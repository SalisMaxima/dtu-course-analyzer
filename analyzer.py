"""
Course data analyzer for DTU Course Analyzer extension.

This module processes scraped course data, calculates percentiles,
and generates the extension data files.
"""

import json
import sys
from Prepender import PrependToFile
from logger_config import get_analyzer_logger

logger = get_analyzer_logger()

if len(sys.argv) != 2:
    logger.error(f'Usage: {sys.argv[0]} <extension-folder-name>')
    sys.exit(1)

# Load raw scraped data
try:
    with open('coursedic.json') as file:
        courseDic = json.load(file)
    logger.info(f"Loaded {len(courseDic)} courses from coursedic.json")
except FileNotFoundError:
    logger.error("coursedic.json not found. Run scraper.py first.")
    sys.exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON in coursedic.json: {e}")
    sys.exit(1)

db = {}
grades = ["-3", "00", "02", "4", "7", "10", "12"]

# Collection lists for percentile calculation
pass_percentages = []
workloads = []
qualityscores = []
avg = []


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


def insertPercentile(lst: list, tag: str) -> list:
    """
    Calculate and insert percentile rankings for a metric.

    Modifies the global `db` dictionary with percentile values.

    Args:
        lst: List of [courseN, value] pairs
        tag: Key name for storing percentile in db

    Returns:
        The modified list with percentile values appended
    """
    global db

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


# Calculate all percentiles
insertPercentile(pass_percentages, "pp")
insertPercentile(avg, "avgp")
insertPercentile(qualityscores, "qualityscore")
insertPercentile(workloads, "workload")

# Calculate lazy score (combination of pass rate and low workload)
lazyscores = []
for courseN, course in db.items():
    if "pp" in course and "workload" in course:
        lazyscores.append([courseN, course['pp'] + course['workload']])

insertPercentile(lazyscores, "lazyscore")

# Remove courses with no data
empty_keys = [k for k, v in db.items() if not v]
for k in empty_keys:
    del db[k]

logger.info(f"Final dataset contains {len(db)} courses with data")

# Generate extension data file
folder = sys.argv[1]
extFilename = f'{folder}/db/data.js'

try:
    with open(extFilename, 'w') as outfile:
        json.dump(db, outfile)

    with PrependToFile(extFilename) as f:
        f.write_line('window.data = ')

    logger.info(f"Wrote extension data to {extFilename}")
except IOError as e:
    logger.error(f"Failed to write extension data: {e}")
    sys.exit(1)

# Also save as plain JSON for debugging
try:
    with open('data.json', 'w') as outfile:
        json.dump(db, outfile, indent=2)
    logger.info("Wrote formatted data to data.json")
except IOError as e:
    logger.warning(f"Failed to write data.json: {e}")

# Generate HTML table for dashboard
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
    with open("templates/db.html", 'r') as file:
        content = file.read()

    content = content.replace('$table', table)

    with open(f"{folder}/db.html", 'w') as file:
        file.write(content)

    logger.info(f"Generated {folder}/db.html")
except IOError as e:
    logger.error(f"Failed to generate db.html: {e}")
    sys.exit(1)

# Generate init_table.js
try:
    with open("templates/init_table.js", 'r') as file:
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
        searchable_columns += f', {{ type: "non-empty", {sort_str}"aTargets": [ {col_idx} ] }}'

    content = content.replace('$searchable_columns', searchable_columns)

    with open(f"{folder}/js/init_table.js", 'w') as file:
        file.write(content)

    logger.info(f"Generated {folder}/js/init_table.js")
except IOError as e:
    logger.error(f"Failed to generate init_table.js: {e}")
    sys.exit(1)

logger.info("Analysis complete!")
