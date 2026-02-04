"""
Course data analyzer for DTU Course Analyzer extension.

This module processes scraped course data, calculates percentiles,
and generates the extension data files.
"""

import json
import sys
from typing import Dict, List, Any, Optional, Tuple

# Import from our modules
from ..config import config
from ..utils.logger import setup_logger
from ..utils.prepender import PrependToFile

logger = setup_logger('analyzer', 'analyzer.log')


def calcScore(dic: dict, bestOptionFirst: bool) -> float:
    """
    Calculate weighted score from survey responses.

    Args:
        dic: Dictionary of question responses
        bestOptionFirst: True if higher response index = worse

    Returns:
        Weighted average score (1-5 scale)
    """
    score = 0
    total_votes = 0

    for id, votes in dic.items():
        if id == "question":
            continue
        try:
            vote_count = int(votes)
            option_id = int(id)
            if bestOptionFirst:
                score += (5 - option_id) * vote_count
            else:
                score += (1 + option_id) * vote_count
            total_votes += vote_count
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse vote data: {id}={votes}, error: {e}")
            continue

    if total_votes == 0:
        raise ValueError("No valid votes found")

    return score / total_votes


def select_best_sheet(sheets: list) -> dict | None:
    """
    Select the most representative data sheet from multiple semesters.

    Prefers sheets with more participants, but also considers
    minimum sample sizes.

    Args:
        sheets: List of semester data sheets

    Returns:
        Best sheet, or None if no valid sheet found
    """
    if not sheets:
        return None

    sheet = sheets[0]

    # If there's a second sheet with significantly more participants, use it
    if len(sheets) >= 2:
        if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
            sheet = sheets[1]

    # Require minimum sample size
    if sheet.get("participants", 0) < 5:
        return None

    return sheet


def insertPercentile(lst: List[List], tag: str, db: Dict) -> List[List]:
    """
    Calculate and insert percentile rankings for a metric.

    Modifies the provided `db` dictionary with percentile values.

    Args:
        lst: List of [courseN, value] pairs
        tag: Key name for storing percentile in db
        db: Database dictionary to update

    Returns:
        The modified list with percentile values appended
    """
    if not lst:
        logger.warning(f"No data to calculate percentiles for '{tag}'")
        return lst

    # Sort by course number first (tie-breaker), then by value
    lst.sort(key=lambda x: x[0], reverse=True)
    lst.sort(key=lambda x: x[1])

    # Assign rank indices (same value = same rank)
    prev_val = None
    index = -1
    for course in lst:
        val = course[1]
        if val != prev_val:
            index += 1
        course.append(index)
        prev_val = val

    # Calculate percentiles
    max_index = index if index > 0 else 1  # Avoid division by zero
    for course in lst:
        percentile = round(100 * course[2] / max_index, 1)
        course.append(percentile)
        db[course[0]][tag] = percentile

    logger.info(f"Calculated {tag} percentiles for {len(lst)} courses")
    return lst


def process_courses(courseDic: Dict) -> Dict:
    """
    Process raw course data into analyzed database.

    Args:
        courseDic: Raw scraped course data

    Returns:
        Processed database with percentiles and metrics
    """
    db = {}
    grades = ["-3", "00", "02", "4", "7", "10", "12"]

    # Collection lists for percentile calculation
    pass_percentages = []
    workloads = []
    qualityscores = []
    avg = []

    # Process each course
    for courseN, course in courseDic.items():
        logger.debug(f"Processing course: {courseN}")
        db[courseN] = {}
        db_sheet = db[courseN]

        for categoryN, sheets in course.items():
            if categoryN == "name":
                db_sheet["name"] = sheets
                continue
            if categoryN == "name_en":
                db_sheet["name_en"] = sheets
                continue

            sheet = select_best_sheet(sheets)
            if sheet is None:
                continue

            if categoryN == "grades":
                # Extract pass percentage (required)
                if "pass_percentage" not in sheet:
                    logger.debug(f"Course {courseN}: No pass_percentage in grades")
                    continue

                db_sheet["passpercent"] = sheet["pass_percentage"]
                pass_percentages.append([courseN, sheet["pass_percentage"]])

                # Extract average grade (optional)
                if "avg" in sheet:
                    try:
                        avg_val = float(sheet["avg"])
                        db_sheet["avg"] = avg_val
                        avg.append([courseN, avg_val])
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Course {courseN}: Invalid avg value: {e}")

                # Extract participants (total course attendees)
                if "participants" in sheet:
                    db_sheet["grade_participants"] = sheet["participants"]

                # Extract individual grades (optional)
                db_sheet["grades"] = {}
                for grade in grades:
                    if grade in sheet:
                        db_sheet["grades"][grade] = sheet[grade]

            elif categoryN == "reviews":
                # Determine scoring direction
                bestOptionFirst = None
                firstOption = sheet.get("firstOption", "")

                if firstOption == "Helt uenig":
                    bestOptionFirst = False
                elif firstOption == "Helt enig":
                    bestOptionFirst = True
                else:
                    logger.debug(f"Course {courseN}: Unknown firstOption '{firstOption}', skipping reviews")
                    continue

                # Extract participants (people who gave feedback)
                if "participants" in sheet:
                    db_sheet["review_participants"] = sheet["participants"]

                # Calculate workload score (question 2.1)
                if "2.1" in sheet:
                    try:
                        workload_score = calcScore(sheet["2.1"], True)
                        workloads.append([courseN, workload_score])
                    except (ValueError, KeyError) as e:
                        logger.debug(f"Course {courseN}: Could not calculate workload: {e}")

                # Calculate quality score (question 1.1)
                if "1.1" in sheet:
                    try:
                        quality_score = calcScore(sheet["1.1"], bestOptionFirst)
                        qualityscores.append([courseN, quality_score])
                    except (ValueError, KeyError) as e:
                        logger.debug(f"Course {courseN}: Could not calculate quality score: {e}")

    # Calculate all percentiles
    insertPercentile(pass_percentages, "pp", db)
    insertPercentile(avg, "avgp", db)
    insertPercentile(qualityscores, "qualityscore", db)
    insertPercentile(workloads, "workload", db)

    # Calculate lazy score (combination of pass rate and low workload)
    # Build from workloads list instead of iterating all courses in db for efficiency
    lazyscores = []
    for entry in workloads:
        courseN = entry[0]
        if courseN in db and "pp" in db[courseN] and "workload" in db[courseN]:
            lazyscores.append([courseN, db[courseN]['pp'] + db[courseN]['workload']])

    insertPercentile(lazyscores, "lazyscore", db)

    # Remove courses with no data
    empty_keys = [k for k, v in db.items() if not v]
    for k in empty_keys:
        del db[k]

    logger.info(f"Final dataset contains {len(db)} courses with data")
    return db


def generate_extension_data(db: Dict, folder: str):
    """
    Generate extension data files (data.js and data.json).

    Args:
        db: Processed course database
        folder: Target folder for extension files
    """
    extFilename = f'{folder}/db/data.js'

    try:
        with open(extFilename, 'w') as outfile:
            json.dump(db, outfile)

        with PrependToFile(extFilename) as f:
            f.write_line('window.data = ')

        logger.info(f"Wrote extension data to {extFilename}")
    except IOError as e:
        logger.error(f"Failed to write extension data: {e}")
        raise

    # Also save as plain JSON for debugging
    try:
        with open(config.paths.data_json_file, 'w') as outfile:
            json.dump(db, outfile, indent=2)
        logger.info(f"Wrote formatted data to {config.paths.data_json_file}")
    except IOError as e:
        logger.warning(f"Failed to write data.json: {e}")


def generate_html_table(db: Dict, folder: str):
    """
    Generate HTML table for dashboard (db.html).

    Args:
        db: Processed course database
        folder: Target folder for extension files
    """
    # Note: name_en is hidden but searchable for bilingual search
    headNames = [
        ["name", "Name", False],           # Danish name (visible by default)
        ["name_en", "Name (EN)", True],    # English name (hidden, for search)
        ["avg", "Average Grade", False],
        ["avgp", "Average Grade Percentile", False],
        ["passpercent", "Percent Passed", False],
        ["grade_participants", "Total Students", False],
        ["review_participants", "Feedback Count", False],
        ["qualityscore", "Course Rating", False],
        ["workload", "Workload", False],
        ["lazyscore", "Lazy Score Percentile", False]
    ]

    # Build table using list for efficient string concatenation
    table_parts = ['<table id="example" class="display" cellspacing="0" width="100%"><thead><tr>']
    table_parts.append('<th>Course</th>')
    for header in headNames:
        hidden_class = ' class="hidden-col"' if header[2] else ''
        table_parts.append(f'<th{hidden_class}>{header[1]}</th>')
    table_parts.append('</tr></thead><tbody>')

    for course, data in db.items():
        table_parts.append('<tr>')
        table_parts.append(f'<td><a href="http://kurser.dtu.dk/course/{course}">{course}</a></td>')
        for header in headNames:
            key = header[0]
            val = str(data.get(key, ""))
            hidden_class = ' class="hidden-col"' if header[2] else ''
            table_parts.append(f'<td{hidden_class}>{val}</td>')
        table_parts.append('</tr>')
    table_parts.append('</tbody></table>')

    # Join all parts into final table string
    table = ''.join(table_parts)

    # Read template and generate db.html
    try:
        with open(config.paths.template_dir / "db.html", 'r') as file:
            content = file.read()

        content = content.replace('$table', table)

        with open(f"{folder}/db.html", 'w') as file:
            file.write(content)

        logger.info(f"Generated {folder}/db.html")
    except IOError as e:
        logger.error(f"Failed to generate db.html: {e}")
        raise


def generate_init_table_js(db: Dict, folder: str):
    """
    Generate init_table.js configuration file.

    Args:
        db: Processed course database (for column count)
        folder: Target folder for extension files
    """
    headNames = [
        ["name", "Name", False],
        ["name_en", "Name (EN)", True],
        ["avg", "Average Grade", False],
        ["avgp", "Average Grade Percentile", False],
        ["passpercent", "Percent Passed", False],
        ["grade_participants", "Total Students", False],
        ["review_participants", "Feedback Count", False],
        ["qualityscore", "Course Rating", False],
        ["workload", "Workload", False],
        ["lazyscore", "Lazy Score Percentile", False]
    ]

    try:
        with open(config.paths.template_dir / "init_table.js", 'r') as file:
            content = file.read()

        # Column 0: Course code (searchable)
        searchable_columns = '{ "bSearchable": true, "aTargets": [ 0 ] }'
        for i in range(len(headNames)):
            col_idx = i + 1
            key = headNames[i][0]
            is_hidden = headNames[i][2]

            # Both name columns (Danish and English) are searchable
            # Note: Do NOT use bVisible: false - it removes column from DOM
            # Use CSS hidden-col class instead for initial hiding
            if key in ["name", "name_en"]:
                sort_str = '"bSearchable": true,'
            else:
                sort_str = '"asSorting": [ "desc", "asc" ], "bSearchable": false, '
            searchable_columns += f', {{ "type": "non-empty", {sort_str}"aTargets": [ {col_idx} ] }}'

        content = content.replace('$searchable_columns', searchable_columns)

        with open(f"{folder}/js/init_table.js", 'w') as file:
            file.write(content)

        logger.info(f"Generated {folder}/js/init_table.js")
    except IOError as e:
        logger.error(f"Failed to generate init_table.js: {e}")
        raise


def main():
    """Main entry point for the analyzer."""
    if len(sys.argv) != 2:
        logger.error(f'Usage: {sys.argv[0]} <extension-folder-name>')
        return 1

    folder = sys.argv[1]

    # Load raw scraped data
    try:
        with open(config.paths.course_data_file) as file:
            courseDic = json.load(file)
        logger.info(f"Loaded {len(courseDic)} courses from {config.paths.course_data_file}")
    except FileNotFoundError:
        logger.error(f"{config.paths.course_data_file} not found. Run scraper.py first.")
        return 1
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {config.paths.course_data_file}: {e}")
        return 1

    # Process courses and calculate metrics
    db = process_courses(courseDic)

    # Generate all output files
    try:
        generate_extension_data(db, folder)
        generate_html_table(db, folder)
        generate_init_table_js(db, folder)
    except IOError as e:
        logger.error(f"Failed to generate output files: {e}")
        return 1

    logger.info("Analysis complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
