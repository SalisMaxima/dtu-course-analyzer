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
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup
from yarl import URL

from ..analysis.exam_classification import classify_course, extract_schedule, parse_period
from ..config import config
from ..parsers.grade_parser import parse_grades
from ..scrapers.async_scraper import is_login_page, pace_request, retry_delay, RETRY_STATUSES


def extract_histogram_links(html: str, course: str) -> list[dict]:
    found = {}
    for anchor in BeautifulSoup(html, "lxml").find_all("a", href=True):
        url = urlsplit(urljoin(config.scraper.base_url, anchor["href"]))
        if url.hostname != "karakterer.dtu.dk":
            continue
        if not re.fullmatch(rf"/Histogram/\d+/{re.escape(course)}/[^/]+", url.path):
            continue
        canonical = urlunsplit(("http", "karakterer.dtu.dk", url.path, "", ""))
        found.setdefault(canonical, {
            "url": canonical, "link_label": anchor.get_text(" ", strip=True),
            "period": parse_period(canonical),
        })
    return list(found.values())


async def fetch_page(session, url: str) -> str:
    """Use existing pacing/retry policy, but retain individual failures."""
    for attempt in range(config.scraper.max_retries + 1):
        await pace_request()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(
                total=config.scraper.timeout
            )) as response:
                if response.status in RETRY_STATUSES and attempt < config.scraper.max_retries:
                    await asyncio.sleep(min(60, retry_delay(attempt, response.headers.get("Retry-After"))))
                    continue
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                html = await response.text()
                if is_login_page(html, str(response.url)):
                    raise ValueError("authentication_required_or_expired")
                return html
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == config.scraper.max_retries:
                raise ValueError("network_error_or_timeout") from None
            await asyncio.sleep(min(60, retry_delay(attempt)))
    raise ValueError("request_failed")


async def collect_course(session, semaphore, course: str) -> dict:
    record = {"course": course, "schedule": {}, "exams": [], "errors": []}
    async with semaphore:
        for kind, url in (
            ("course", f"{config.scraper.base_url}/course/{course}?lang=en-GB"),
            ("info", f"{config.scraper.base_url}/course/{course}/info?lang=en-GB"),
        ):
            record[f"{kind}_url"] = url
            try:
                html = await fetch_page(session, url)
            except ValueError as exc:
                record["errors"].append({"source": kind, "reason": str(exc)})
                continue
            if kind == "course":
                record["schedule"] = extract_schedule(html)
                soup = BeautifulSoup(html, "lxml")
                heading = soup.find("h2")
                record["name"] = heading.get_text(" ", strip=True) if heading else None
            else:
                record["exams"] = extract_histogram_links(html, course)

        for exam in record["exams"]:
            try:
                html = await fetch_page(session, exam["url"])
                soup = BeautifulSoup(html, "lxml")
                # Retain targeted source evidence for manual review, not login
                # pages, cookies, scripts, or unrelated personal information.
                exam["evidence"] = {
                    "headings": [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])],
                    "tables": [t.get_text(" ", strip=True) for t in soup.find_all("table")],
                }
                exam["grades"] = parse_grades(html, exam["url"])
                if not exam["grades"] or "participants" not in exam["grades"]:
                    exam["error"] = "histogram_parse_failed"
            except ValueError as exc:
                exam["error"] = str(exc)
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
    report["summary"] = dict(Counter(r["status"] for r in report["courses"].values()))
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output / "report.json")
    with (output / "courses.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["course", "status", "schedule", "primary_exam", "primary_url",
                         "resit_exams", "undetermined_exams", "reasons", "errors"])
        for course, row in report["courses"].items():
            primary = row.get("primary_exam") or {}
            writer.writerow([
                course, row["status"], row.get("schedule", {}).get("raw", ""),
                primary.get("period", {}).get("label", ""), primary.get("url", ""),
                json.dumps([e["url"] for e in row.get("resit_exams", [])]),
                json.dumps([e["url"] for e in row.get("undetermined_exams", [])]),
                "; ".join(row.get("reasons", [])), json.dumps(row.get("errors", []) + [
                    {"source": e["url"], "reason": e["error"]}
                    for e in row.get("exams", []) if e.get("error")
                ]),
            ])
    summary = ["# Exam classification diagnostic", "",
               "Provisional schedule-based assignments; not measured classification accuracy.", "",
               f"Requested courses: {len(report['courses'])}", ""]
    summary.extend(f"- {status}: {count}" for status, count in sorted(report["summary"].items()))
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
        "schema_version": 1, "rule_version": "schedule-hypothesis-v1",
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
            headers={"User-Agent": "DTU-Course-Analyzer/diagnostic"},
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--courses", help="Comma-separated course IDs; default: entire course file")
    parser.add_argument("--course-file", type=Path, default=config.paths.course_numbers_file)
    parser.add_argument("--output", type=Path, default=Path("exam-classification-report"))
    args = parser.parse_args(argv)
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
