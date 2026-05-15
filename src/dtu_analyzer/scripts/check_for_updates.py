"""
Weekly DTU course-data change detector.

Cheap probe that does NOT scrape grades. It compares:

1. The current course-number list on kurser.dtu.dk against the committed
   baseline at ``source-code/coursenumbers.txt`` (added/removed courses).
2. A small sample of active courses' grade-page URLs against the URLs
   already stored in ``source-code/coursedic.json`` (new semesters).

Writes ``check_report.json`` in the repo root and always exits 0 (the
calling workflow branches on the JSON, not the exit status). The only
exception is auth/setup failure, which exits non-zero.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from ..config import config
from ..utils.logger import setup_logger
from .get_course_numbers import get_course_numbers

logger = setup_logger('check_updates', 'check_updates.log')

BASE_URL = config.scraper.base_url
TIMEOUT = config.scraper.timeout
MAX_CONCURRENT = config.scraper.max_concurrent

DEFAULT_SAMPLE_SIZE = int(os.getenv('CHECK_SAMPLE_SIZE', '8'))
REPORT_FILE = config.paths.root_dir / 'check_report.json'

# The committed baselines (under source-code/, NOT data/, which holds the
# freshly produced files from the current run).
BASELINE_NUMBERS_FILE = config.paths.root_dir / 'source-code' / 'coursenumbers.txt'
BASELINE_COURSEDIC_FILE = config.paths.root_dir / 'source-code' / 'coursedic.json'


def load_baseline_course_numbers() -> set[str]:
    """Read the comma-separated committed baseline of course numbers."""
    if not BASELINE_NUMBERS_FILE.exists():
        logger.warning(f"Baseline {BASELINE_NUMBERS_FILE} missing; treating as empty.")
        return set()
    raw = BASELINE_NUMBERS_FILE.read_text().strip()
    if not raw:
        return set()
    return {n.strip() for n in raw.split(',') if n.strip()}


def load_current_course_numbers() -> set[str]:
    """Read the freshly produced course-numbers file from this run."""
    path = config.paths.course_numbers_file
    raw = path.read_text().strip()
    return {n.strip() for n in raw.split(',') if n.strip()}


def pick_sample(coursedic: dict, size: int) -> list[str]:
    """Pick the N courses with the most recent-semester participants.

    Sampling by recent activity keeps the probe meaningful — obscure or
    retired courses rarely get new semester data.
    """
    scored: list[tuple[int, str]] = []
    for course_n, data in coursedic.items():
        grades = data.get('grades') or []
        if not grades:
            continue
        # `grades` is a list of semester dicts; treat the first entry as
        # the most recent (matches how the scraper stores them).
        recent = grades[0]
        try:
            participants = int(recent.get('participants') or 0)
        except (TypeError, ValueError):
            participants = 0
        scored.append((participants, course_n))
    scored.sort(reverse=True)
    return [c for _, c in scored[:size]]


def existing_grade_urls(coursedic: dict, course_n: str) -> set[str]:
    """All grade-page URLs we already have stored for a given course."""
    urls: set[str] = set()
    for grade in coursedic.get(course_n, {}).get('grades', []) or []:
        url = grade.get('url')
        if url:
            urls.add(url.strip())
    return urls


def normalize_grade_href(href: str) -> str:
    """Turn a relative or absolute karakterer href into an absolute URL."""
    href = href.strip()
    if href.startswith('http://') or href.startswith('https://'):
        return href
    if not href.startswith('/'):
        href = '/' + href
    return f"{BASE_URL}{href}"


async def fetch_grade_links_for_course(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    course_n: str,
) -> tuple[str, set[str]]:
    """Fetch a course's info page and extract all karakterer links."""
    url = f"{BASE_URL}/course/{course_n}/info"
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                if resp.status != 200:
                    logger.warning(f"HTTP {resp.status} for {url}")
                    return course_n, set()
                html = await resp.text()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return course_n, set()

    soup = BeautifulSoup(html, 'lxml')
    found: set[str] = set()
    for a in soup.find_all('a'):
        href = a.get('href')
        if href and 'karakterer' in href:
            found.add(normalize_grade_href(href))
    return course_n, found


async def probe_new_semesters(
    sample_courses: list[str],
    coursedic: dict,
) -> list[dict]:
    """For each sampled course, return any grade URLs not in the baseline."""
    try:
        session_cookie = config.paths.secret_file.read_text().strip()
    except FileNotFoundError:
        logger.error(f"{config.paths.secret_file} missing; cannot probe semesters.")
        return []

    cookies = {'ASP.NET_SessionId': session_cookie}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept-Encoding': 'gzip, deflate',
    }
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    new_semesters: list[dict] = []
    async with aiohttp.ClientSession(connector=connector, cookies=cookies, headers=headers) as session:
        tasks = [fetch_grade_links_for_course(session, semaphore, c) for c in sample_courses]
        for coro in asyncio.as_completed(tasks):
            course_n, found_urls = await coro
            baseline = existing_grade_urls(coursedic, course_n)
            # Compare normalized — baseline urls in coursedic may be stored
            # with or without scheme; normalize both sides.
            baseline_norm = {normalize_grade_href(u) for u in baseline}
            for url in sorted(found_urls - baseline_norm):
                new_semesters.append({'course': course_n, 'url': url})
                logger.info(f"New semester for {course_n}: {url}")
    return new_semesters


def write_report(report: dict) -> None:
    REPORT_FILE.write_text(json.dumps(report, indent=2, sort_keys=True))
    logger.info(f"Wrote report to {REPORT_FILE}")


def main() -> int:
    logger.info("Starting weekly DTU course-data check.")

    # Step 1: refresh course-number list (writes data/coursenumbers.txt).
    if not get_course_numbers():
        logger.error("Failed to fetch current course numbers; aborting.")
        return 1

    baseline = load_baseline_course_numbers()
    current = load_current_course_numbers()
    added = sorted(current - baseline)
    removed = sorted(baseline - current)
    logger.info(
        f"Course list diff: {len(added)} added, {len(removed)} removed "
        f"(baseline={len(baseline)}, current={len(current)})."
    )

    # Step 2: load coursedic.json baseline and pick a sample for probing.
    new_semesters: list[dict] = []
    sample: list[str] = []
    if BASELINE_COURSEDIC_FILE.exists():
        try:
            coursedic = json.loads(BASELINE_COURSEDIC_FILE.read_text())
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse {BASELINE_COURSEDIC_FILE}: {e}")
            coursedic = {}
        if coursedic:
            sample = pick_sample(coursedic, DEFAULT_SAMPLE_SIZE)
            logger.info(f"Probing {len(sample)} sample courses for new semesters: {sample}")
            new_semesters = asyncio.run(probe_new_semesters(sample, coursedic))
    else:
        logger.warning(f"{BASELINE_COURSEDIC_FILE} missing; skipping semester probe.")

    has_changes = bool(added or removed or new_semesters)
    report = {
        'has_changes': has_changes,
        'added_courses': added,
        'removed_courses': removed,
        'new_semesters': new_semesters,
        'checked_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'sample_size': len(sample),
        'baseline_course_count': len(baseline),
        'current_course_count': len(current),
    }
    write_report(report)

    if has_changes:
        logger.info(
            f"Changes detected — added={len(added)} removed={len(removed)} "
            f"new_semesters={len(new_semesters)}"
        )
    else:
        logger.info("No changes detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
