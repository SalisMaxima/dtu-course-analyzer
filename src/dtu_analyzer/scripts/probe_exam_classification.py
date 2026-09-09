"""Collect evidence and report tentative ordinary/resit assignments per course."""

import argparse
import asyncio
from collections import Counter
from http.cookies import SimpleCookie
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup
from yarl import URL

from ..analysis.exam_classification import classify_course, extract_schedule, parse_period, schedule_from_text
from ..analysis.analyzer import extract_grade_results
from ..analysis.course_history_reviews import APPROVED_HISTORY, EXTRA_HISTORY_URLS
from ..config import config
from ..parsers.grade_parser import parse_grades
from ..scrapers.async_scraper import is_login_page, pace_request, retry_delay, RETRY_STATUSES, course_wrapper_url

SCHEMA_VERSION = 5
RULE_VERSION = "schedule-hypothesis-v9-reviewed-recovery"

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
)


def extract_histogram_links(html: str, course: str) -> list[dict]:
    found = {}
    for anchor in BeautifulSoup(html, "lxml").find_all("a", href=True):
        url = urlsplit(urljoin(config.scraper.base_url, anchor["href"]))
        if url.hostname != "karakterer.dtu.dk":
            continue
        match = re.fullmatch(r"/Histogram/\d+/((?=[0-9A-Z]{0,4}[0-9])[0-9A-Z]{5}(?:-[0-9]+)?)/[^/]+", url.path)
        if not match:
            continue
        histogram_course = match[1]
        canonical = urlunsplit(("https", "karakterer.dtu.dk", url.path, "", ""))
        found.setdefault(canonical, {
            "url": canonical, "link_label": anchor.get_text(" ", strip=True),
            "period": parse_period(canonical),
            "histogram_course": histogram_course,
            "identity_status": ("exact_course_id" if histogram_course == course else
                                "variant_requires_review" if histogram_course.startswith(course + "-")
                                else "different_course_requires_review"),
        })
    return list(found.values())


def diagnostic_url(url: str) -> str:
    """Retain routing information without authentication query parameters."""
    parsed = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query)
                       if k in {'lang', 'forceLogin'}])
    return urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, query, ''))


def page_evidence(html: str) -> dict:
    soup = BeautifulSoup(html, 'lxml')
    labels = []
    for row in soup.find_all('tr'):
        cells = row.find_all(['td', 'th'], recursive=False)
        if cells:
            labels.append(cells[0].get_text(' ', strip=True)[:160])
    return {
        'title': soup.title.get_text(' ', strip=True)[:200] if soup.title else None,
        'headings': [h.get_text(' ', strip=True)[:200] for h in soup.find_all(['h1', 'h2'])][:20],
        'table_labels': labels[:80],
        'iframe_count': len(soup.find_all('iframe')),
    }


def distribution_suppressed(text: str) -> bool:
    text = " ".join(text.split()).lower()
    return bool(re.search(
        r"fordelingen vises ikke da tre eller færre|"
        r"distribution (?:is not shown|is hidden).*?(?:three|3) or fewer", text))


def info_evidence(html: str, url: str, course: str) -> dict:
    """Bounded evidence from public course/result content, never raw page HTML."""
    if is_login_page(html, url) or BeautifulSoup(html, "lxml").select_one('input[type="password"]'):
        return {"state": "authentication_required_or_expired"}
    soup = BeautifulSoup(html, "lxml")
    for element in soup.select("script, style, form, input, nav, header, footer"):
        element.decompose()
    text = soup.get_text(" ", strip=True)
    anchors = soup.find_all("a", href=True)
    relevant = []
    for anchor in anchors:
        target = urlsplit(urljoin(url, anchor["href"]))
        if (target.hostname in {"kurser.dtu.dk", "karakterer.dtu.dk"}
                and re.fullmatch(r"/(?:course/[0-9A-Z]{5}(?:/info)?|Histogram/\d+/[0-9A-Z]{5}(?:-[0-9]+)?/[A-Za-z]+-\d+)", target.path)):
            relevant.append(diagnostic_url(urlunsplit(target)))
    # Capture only result-related text nodes, excluding contact details and URLs.
    excerpts = []
    for node in soup.stripped_strings:
        if (re.search(r"exam|grade|result|karakter|eksamen", node, re.I)
                and not re.search(r"@|https?://|token|password|secret|cookie", node, re.I)):
            excerpts.append(node[:250])
    explicit_none = bool(re.search(
        r"no (?:published )?(?:exam results|grade distributions|results)(?: available| found| published)?\b|"
        r"ingen (?:offentliggjorte )?(?:eksamensresultater|karakterfordelinger|resultater)\b", text, re.I))
    links = extract_histogram_links(html, course)
    state = ("links_found" if links else "no_published_results" if explicit_none
             else "empty_response" if not html.strip()
             else "no_links_unknown" if re.search(rf"\b{re.escape(course)}\b", text)
             else "info_page_unrecognized")
    return {"state": state, "link_count": len(anchors),
            "evaluation_link_count": len({urljoin(url, a["href"]) for a in anchors
                                          if urlsplit(urljoin(url, a["href"])).hostname == "evaluering.dtu.dk"}),
            "predecessor_courses": sorted(set(re.findall(r"Prior course:\s*([0-9A-Z]{5})\b", text, re.I))),
            "histogram_link_count": len(links), "relevant_links": list(dict.fromkeys(relevant))[:30],
            "course_content_excerpts": excerpts[:8]}


def read_distribution(exam: dict, html: str) -> None:
    """Store availability independently of seasonal exam classification."""
    soup = BeautifulSoup(html, "lxml")
    exam["evidence"] = {
        "headings": [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])],
        "tables": [t.get_text(" ", strip=True) for t in soup.find_all("table")],
    }
    histogram_course = urlsplit(exam["url"]).path.split("/")[-2]
    base_course = histogram_course.split("-")[0]
    exam["histogram_title"] = next(
        (heading for heading in exam["evidence"]["headings"]
         if re.match(rf"^{re.escape(base_course)}(?:-[0-9]+)?\b", heading)), None)
    if distribution_suppressed(soup.get_text(" ", strip=True)):
        exam.update(distribution_status="suppressed", grades=None)
        return
    exam["grades"] = parse_grades(html, exam["url"])
    if not exam["grades"] or "participants" not in exam["grades"]:
        exam.update(distribution_status="failed", error="histogram_parse_failed")
    else:
        exam["distribution_status"] = "published"
        exam["result_counts"] = result_count_check(exam["grades"])


def result_count_check(sheet: dict) -> dict:
    retained, grading_scale = extract_grade_results(sheet)
    retained_total = sum(int(v) for v in retained.values())
    metadata = {'timestamp', 'participants', 'pass_percentage', 'avg', 'url'}
    source_total = sum(int(v) for k, v in sheet.items() if k not in metadata)
    participants = sheet.get('participants')
    return {'source_total': source_total, 'retained_total': retained_total,
            'participants': participants,
            'all_categories_retained': retained_total == source_total,
            'matches_participants': source_total == participants,
            'grading_scale': grading_scale,
            'participant_difference': participants - source_total if participants is not None else None}


async def fetch_page(session, url: str, diagnostics=None, _frame_depth=0) -> str:
    """Retry one unexpected login response from the original public URL.

    Wrapper recursion uses the inner fetcher, so the retry budget cannot multiply.
    A second login response still fails; no authentication is bypassed.
    """
    for login_attempt in range(2):
        try:
            return await _fetch_page(session, url, diagnostics, _frame_depth)
        except ValueError as exc:
            if str(exc) not in {"authentication_required_or_expired", "authentication_wrapper_unresolved"} or login_attempt:
                raise
            await asyncio.sleep(2)


async def _fetch_page(session, url: str, diagnostics=None, _frame_depth=0) -> str:
    """Use existing pacing/retry policy, but retain individual failures."""
    for attempt in range(config.scraper.max_retries + 1):
        await pace_request()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(
                total=config.scraper.timeout
            )) as response:
                final_url = str(response.url)
                attempt_info = {'requested_url': diagnostic_url(url),
                                'final_url': diagnostic_url(final_url), 'status': response.status}
                if diagnostics is not None:
                    diagnostics.setdefault('attempts', []).append(attempt_info)
                if response.status in RETRY_STATUSES and attempt < config.scraper.max_retries:
                    await asyncio.sleep(min(60, retry_delay(attempt, response.headers.get("Retry-After"))))
                    continue
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                html = await response.text()
                attempt_info["content_type"] = response.headers.get("Content-Type", "")
                attempt_info["response_bytes"] = len(html.encode("utf-8"))
                if is_login_page(html, final_url) or BeautifulSoup(html, "lxml").select_one('input[type="password"]'):
                    attempt_info["state"] = "authentication_required_or_expired"
                    raise ValueError("authentication_required_or_expired")
                if diagnostics is not None:
                    attempt_info['page'] = page_evidence(html)
                wrapper = course_wrapper_url(html, final_url)
                if wrapper:
                    if _frame_depth:
                        raise ValueError('authentication_wrapper_unresolved')
                    return await _fetch_page(session, wrapper, diagnostics, _frame_depth=1)
                return html
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == config.scraper.max_retries:
                raise ValueError("network_error_or_timeout") from None
            await asyncio.sleep(min(60, retry_delay(attempt)))
    raise ValueError("request_failed")


async def collect_course(session, semaphore, course: str) -> dict:
    record = {"course": course, "schedule": {}, "exams": [], "errors": [], "pages": {}}
    async with semaphore:
        for kind, url in (
            ("course", f"{config.scraper.base_url}/course/{course}?lang=en-GB"),
            ("info", f"{config.scraper.base_url}/course/{course}/info?lang=en-GB"),
        ):
            record[f"{kind}_url"] = url
            diagnostics = record['pages'][kind] = {}
            try:
                html = await fetch_page(session, url, diagnostics)
            except ValueError as exc:
                record["errors"].append({"source": kind, "reason": str(exc)})
                continue
            if kind == "course":
                record["schedule"] = extract_schedule(html, course)
                soup = BeautifulSoup(html, "lxml")
                heading = soup.find("h2")
                record["name"] = heading.get_text(" ", strip=True) if heading else None
                if not record['schedule'].get('raw'):
                    reason = 'schedule_field_missing' if record['name'] else 'course_page_unrecognized'
                    record['errors'].append({'source': kind, 'reason': reason})
            else:
                record["exams"] = extract_histogram_links(html, course)
                diagnostics["content"] = info_evidence(html, url, course)
                state = diagnostics["content"]["state"]
                if state in {"info_page_unrecognized", "empty_response"}:
                    record["errors"].append({"source": kind, "reason": state})

        # A reviewed equivalence may have no links on the current course's page.
        # Visit only explicitly approved source info pages; never follow arbitrary
        # predecessor chains or silently approve newly discovered identities.
        present_sources = {e["histogram_course"] for e in record["exams"]}
        for source in APPROVED_HISTORY.get(course, {}):
            if source in present_sources:
                continue
            diagnostics = record["pages"].setdefault("reviewed_sources", {}).setdefault(source, {})
            try:
                html = await fetch_page(session, f"{config.scraper.base_url}/course/{source}/info?lang=en-GB", diagnostics)
                diagnostics["content"] = info_evidence(html, f"{config.scraper.base_url}/course/{source}/info", source)
                extra = [e for e in extract_histogram_links(html, course) if e["histogram_course"] == source]
                record["exams"].extend(extra)
            except ValueError as exc:
                record["errors"].append({"source": "reviewed_history:" + source, "reason": str(exc)})

        existing = {e["url"] for e in record["exams"]}
        for url in EXTRA_HISTORY_URLS.get(course, []):
            if url not in existing:
                record["exams"].append({"url": url, "period": parse_period(url),
                    "histogram_course": course, "identity_status": "exact_course_id",
                    "link_origin": "previously_collected_history"})

        for exam in record["exams"]:
            try:
                html = await fetch_page(session, exam["url"])
                read_distribution(exam, html)
            except ValueError as exc:
                exam.update(distribution_status="failed", error=str(exc))
    return classify_course(record)


async def collect_registered_course(session, semaphore, course: str) -> dict:
    """A malformed course must not discard the other course registrations."""
    try:
        return await collect_course(session, semaphore, course)
    except Exception as exc:
        return classify_course({
            "course": course, "schedule": {}, "exams": [],
            "errors": [{"source": "collector", "reason": type(exc).__name__}],
        })


def write_reports(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report["schema_version"] = SCHEMA_VERSION
    report["rule_version"] = RULE_VERSION
    report["summary"] = dict(Counter(r["status"] for r in report["courses"].values()))
    exams = [e for row in report["courses"].values() for e in row.get("exams", [])]
    report["distribution_summary"] = dict(Counter(e.get("distribution_status", "unknown") for e in exams))
    report["variant_histograms"] = sum(e.get("identity_status") == "variant_requires_review" for e in exams)
    report["different_course_histograms"] = sum(e.get("identity_status") == "different_course_requires_review" for e in exams)
    report["count_summary"] = {
        "category_retention_failures": sum(not e["result_counts"]["all_categories_retained"]
                                          for e in exams if "result_counts" in e),
        "participant_discrepancies": sum(not e["result_counts"]["matches_participants"]
                                       for e in exams if "result_counts" in e),
    }
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output / "report.json")
    with (output / "courses.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["course", "status", "primary_status", "resit_status", "schedule", "primary_exam", "primary_url",
                         "resit_exams", "undetermined_exams", "reasons", "errors",
                         "primary_distribution_status", "suppressed_histograms", "failed_histograms",
                         "category_retention_failures", "participant_discrepancies", "info_state", "variant_urls", "different_course_urls"])
        for course, row in report["courses"].items():
            primary = row.get("primary_exam") or {}
            writer.writerow([
                course, row["status"], row.get('primary_status', 'not_collected'),
                row.get('resit_status', 'not_collected'), row.get("schedule", {}).get("raw", ""),
                primary.get("period", {}).get("label", ""), primary.get("url", ""),
                json.dumps([e["url"] for e in row.get("resit_exams", [])]),
                json.dumps([e["url"] for e in row.get("undetermined_exams", [])]),
                "; ".join(row.get("reasons", [])), json.dumps(row.get("errors", []) + [
                    {"source": e["url"], "reason": e["error"]}
                    for e in row.get("exams", []) if e.get("error")
                ]),
                primary.get("distribution_status", ""),
                sum(e.get("distribution_status") == "suppressed" for e in row.get("exams", [])),
                sum(e.get("distribution_status") == "failed" for e in row.get("exams", [])),
                sum(not e["result_counts"]["all_categories_retained"] for e in row.get("exams", []) if "result_counts" in e),
                sum(not e["result_counts"]["matches_participants"] for e in row.get("exams", []) if "result_counts" in e),
                row.get("pages", {}).get("info", {}).get("content", {}).get("state", "not_recorded"),
                json.dumps([e["url"] for e in row.get("exams", [])
                            if e.get("identity_status") == "variant_requires_review"]),
                json.dumps([e["url"] for e in row.get("exams", [])
                            if e.get("identity_status") == "different_course_requires_review"]),
            ])
    summary = ["# Exam classification diagnostic", "",
               "Provisional schedule-based assignments; not measured classification accuracy.", "",
               f"Requested courses: {len(report['courses'])}", ""]
    if report.get("replay"):
        summary.extend(["Offline replay of saved evidence; no fresh requests or original schedule markup.", ""])
    summary.extend(f"- {status}: {count}" for status, count in sorted(report["summary"].items()))
    no_resits = sum(row.get('resit_status') == 'none_found_in_collected_links'
                   for row in report['courses'].values())
    summary.extend(['', f'Primary identified, no resit links found: {no_resits}'])
    summary.append(f"Different-course histograms requiring identity review: {report['different_course_histograms']}")
    summary.append(f"Suffixed course histograms requiring identity review: {report['variant_histograms']}")
    summary.extend(f"Distributions {status}: {count}" for status, count in sorted(report["distribution_summary"].items()))
    summary.extend([
        f"Category-retention failures: {report['count_summary']['category_retention_failures']}",
        f"Source participant-total discrepancies: {report['count_summary']['participant_discrepancies']}",
    ])
    count_mismatches = sum(
        not all(e['result_counts'][k] for k in ('all_categories_retained', 'matches_participants'))
        for row in report['courses'].values() for e in row.get('exams', []) if 'result_counts' in e)
    summary.extend([f'Histograms with result-count discrepancies: {count_mismatches}'])
    mixed_histograms = sum(
        e.get('result_counts', {}).get('grading_scale') == 'mixed'
        for row in report['courses'].values() for e in row.get('exams', []))
    summary.extend([f'Mixed numeric/pass-fail histograms requiring review: {mixed_histograms}'])
    if report.get("fatal_error"):
        summary.extend(["", f"Run error: {report['fatal_error']}"])
    reasons = Counter(reason for row in report["courses"].values() for reason in row.get("reasons", []))
    summary.extend(["", "## Unresolved reasons", ""])
    summary.extend(f"- {reason}: {count}" for reason, count in reasons.most_common())
    period_counts = Counter(e["period"]["label"] for row in report["courses"].values()
                            for e in row.get("exams", []))
    summary.extend(["", "## Observed histogram periods", ""])
    summary.extend(f"- {period}: {count}" for period, count in sorted(period_counts.items()))
    summary.extend(["", "See courses.csv for every course and report.json for source evidence.", ""])
    (output / "summary.md").write_text("\n".join(summary), encoding="utf-8")


async def run_probe(courses: list[str], output: Path) -> int:
    report = {
        "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "courses": {c: {"course": c, "status": "pending", "primary_exam": None,
                        "resit_exams": [], "undetermined_exams": [],
                        "reasons": ["not_collected"]} for c in courses},
    }
    write_reports(report, output)
    try:
        cookie = config.paths.secret_file.read_text().strip()
        if not cookie:
            raise ValueError("empty_session_cookie")
        # Host-only, secure cookie: never attach the authenticated session to
        # public HTTP histograms or redirects to other hosts.
        jar = aiohttp.CookieJar()
        scoped = SimpleCookie()
        scoped["ASP.NET_SessionId"] = cookie
        scoped["ASP.NET_SessionId"]["secure"] = True
        jar.update_cookies(scoped, response_url=URL(config.scraper.base_url))
        concurrency = max(1, config.scraper.max_concurrent)
        async with aiohttp.ClientSession(
            cookie_jar=jar, connector=aiohttp.TCPConnector(limit=concurrency),
            headers={"User-Agent": BROWSER_USER_AGENT},
        ) as session:
            semaphore = asyncio.Semaphore(concurrency)
            tasks = [collect_registered_course(session, semaphore, c) for c in courses]
            for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
                row = await task
                report["courses"][row["course"]] = row
                print(f"{row['course']}: {row['status']}", flush=True)
                if completed % 25 == 0:
                    write_reports(report, output)
    except (OSError, ValueError) as exc:
        report["fatal_error"] = "session_file_missing_or_unreadable" if isinstance(exc, OSError) else str(exc)
        for row in report["courses"].values():
            if row["status"] == "pending":
                row.update(status="error", reasons=["collection_not_completed"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_reports(report, output)
    return int(bool(report.get("fatal_error")) or any(
        r["status"] in {"error", "pending"} for r in report["courses"].values()
    ))


def replay_report(source: Path, output: Path) -> dict:
    if source.resolve().parent == output.resolve():
        raise ValueError("Replay output must differ from the source directory")
    report = json.loads(source.read_text(encoding="utf-8"))
    report["replay"] = {"source_schema_version": report.get("schema_version"),
                        "reprocessed_at": datetime.now(timezone.utc).isoformat(),
                        "note": "Offline replay; schedule markup and missing info content were not retained."}
    for course, row in report["courses"].items():
        row["schedule"] = schedule_from_text(row.get("schedule", {}).get("raw", ""), course)
        row["schedule"]["basis"] = "legacy_text_replay"
        for exam in row.get("exams", []):
            evidence = " ".join(exam.get("evidence", {}).get("tables", []))
            if exam.get("error") == "histogram_parse_failed" and distribution_suppressed(evidence):
                exam.pop("error")
                exam["distribution_status"] = "suppressed"
            elif exam.get("error"):
                exam["distribution_status"] = "failed"
            elif exam.get("grades"):
                exam["distribution_status"] = "published"
                exam["result_counts"] = result_count_check(exam["grades"])
        report["courses"][course] = classify_course(row)
    write_reports(report, output)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--courses", help="Comma-separated course IDs; default: entire course file")
    parser.add_argument("--course-file", type=Path, default=config.paths.course_numbers_file)
    parser.add_argument("--output", type=Path, default=Path("exam-classification-report"))
    parser.add_argument("--replay", type=Path, help="Reclassify saved report evidence without network access")
    args = parser.parse_args(argv)
    if args.replay:
        replay_report(args.replay, args.output)
        return 0
    try:
        raw = args.courses if args.courses else args.course_file.read_text()
        courses = sorted(set(filter(None, re.split(r"[,\s]+", raw.strip().upper()))))
        if not courses or any(not re.fullmatch(r"[A-Z0-9]{5}", c) for c in courses):
            raise ValueError("Expected at least one five-character course ID")
    except (OSError, ValueError) as exc:
        write_reports({"courses": {}, "fatal_error": str(exc)}, args.output)
        return 1
    return asyncio.run(run_probe(courses, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
