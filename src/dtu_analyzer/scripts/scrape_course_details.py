"""Collect course descriptions and 'Not applicable together with' links.

Fetches the English catalogue page for each course in the bundled dataset, and
the Danish page only when the English one has no description. Uses the main
scraper's pacing, retries and login-page detection.

Usage: dtu-scrape-details [--courses extension/db/data.json] [--output data/course_details.json]
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

import aiohttp
from tqdm.asyncio import tqdm

from ..config import config
from ..parsers.course_page_parser import parse_course_page
from ..scrapers import async_scraper
from ..utils.logger import get_scraper_logger

logger = get_scraper_logger()
DESCRIPTION_FIELDS = ("general_objectives", "learning_objectives", "content")
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
)


def merge_details(english: dict, danish: dict) -> dict:
    """Prefer English text; keep exclusion links found on either page."""
    merged = dict(english)
    if not any(field in english for field in DESCRIPTION_FIELDS):
        for field in DESCRIPTION_FIELDS:
            if field in danish:
                merged[field] = danish[field]
        if any(field in danish for field in DESCRIPTION_FIELDS):
            merged["text_language"] = "da"
    codes = english.get("not_applicable_with", []) + danish.get("not_applicable_with", [])
    if codes:
        merged["not_applicable_with"] = list(dict.fromkeys(codes))
    if "not_applicable_raw" not in merged and "not_applicable_raw" in danish:
        merged["not_applicable_raw"] = danish["not_applicable_raw"]
    return merged


async def fetch_details(session, semaphore, course: str) -> tuple[str, dict | None]:
    async with semaphore:
        base = f"{config.scraper.base_url}/course/{course}"
        try:
            html = await async_scraper.fetch_url(session, f"{base}?lang=en-GB")
            if not html:
                return course, None
            english = parse_course_page(html)
            danish = {}
            if not any(field in english for field in DESCRIPTION_FIELDS):
                danish_html = await async_scraper.fetch_url(session, f"{base}?lang=da-DK")
                danish = parse_course_page(danish_html) if danish_html else {}
            return course, merge_details(english, danish)
        except async_scraper.TimeoutException:
            return course, None


async def collect(courses: list[str], cookie: str | None) -> dict:
    semaphore = asyncio.Semaphore(config.scraper.max_concurrent)
    connector = aiohttp.TCPConnector(limit=config.scraper.max_concurrent)
    cookies = {"ASP.NET_SessionId": cookie} if cookie else None
    headers = {"User-Agent": BROWSER_USER_AGENT}
    results = {}
    async with aiohttp.ClientSession(connector=connector, cookies=cookies, headers=headers) as session:
        tasks = [fetch_details(session, semaphore, course) for course in courses]
        for future in tqdm.as_completed(tasks, total=len(tasks)):
            course, details = await future
            if details is not None:
                results[course] = details
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--courses", type=Path, default=config.paths.extension_dir / "db/data.json",
                        help="Bundled dataset whose course numbers are collected")
    parser.add_argument("--output", type=Path, default=config.paths.data_dir / "course_details.json")
    args = parser.parse_args(argv)

    courses = sorted(json.loads(args.courses.read_text()))
    cookie = None
    try:
        cookie = config.paths.secret_file.read_text().strip()
    except FileNotFoundError:
        logger.warning("No session cookie found; fetching public course pages without one")

    logger.info(f"Collecting descriptions for {len(courses)} courses")
    results = asyncio.run(collect(courses, cookie))
    if async_scraper.auth_failed or async_scraper.timeout_occurred:
        logger.error("Collection stopped early (authentication or timeout); nothing written")
        return 1

    missing = sorted(set(courses) - set(results))
    without_text = sorted(c for c, d in results.items() if not any(f in d for f in DESCRIPTION_FIELDS))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "courses": dict(sorted(results.items())),
    }, ensure_ascii=False, indent=1) + "\n")
    logger.info(f"Wrote {len(results)} courses to {args.output}; "
                f"{len(missing)} not fetched, {len(without_text)} without description text")
    if missing:
        logger.warning(f"Not fetched: {', '.join(missing[:50])}")
    # Most pages must parse, or DTU's markup has changed and the output is useless
    if len(results) - len(without_text) < 0.9 * len(courses):
        logger.error("Fewer than 90% of courses have description text; check the course page parser")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
