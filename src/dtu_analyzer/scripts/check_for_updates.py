"""
Weekly DTU course-data change detector.

Cheap probe that does NOT scrape grades. It compares:

1. The current course-number list on kurser.dtu.dk against the committed
   baseline at ``data/coursenumbers.txt`` (added/removed courses).
2. Current active courses' grade-page URLs against the URLs already stored
   in ``data/coursedic.json`` (new semesters).

Writes ``check_report.json`` in the repo root whenever possible. Exits non-zero
for setup/probe failures while still preserving any course-list diff in the report.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import aiohttp
from bs4 import BeautifulSoup

from ..config import config
from ..utils.logger import setup_logger
from .get_course_numbers import get_course_numbers

logger = setup_logger('check_updates', 'check_updates.log')

BASE_URL = config.scraper.base_url
TIMEOUT = config.scraper.timeout
MAX_CONCURRENT = config.scraper.max_concurrent

REPORT_FILE = config.paths.root_dir / 'check_report.json'
GRADE_PATH_RE = re.compile(r"^/Histogram/\d+/\d{5}/[^/?#]+$")

# The committed baselines updated by the full scrape workflow. Keep legacy
# source-code fallbacks so the first run after this change still has a baseline.
BASELINE_NUMBERS_FILE = config.paths.course_numbers_file
BASELINE_COURSEDIC_FILE = config.paths.course_data_file
LEGACY_NUMBERS_FILE = config.paths.root_dir / 'source-code' / 'coursenumbers.txt'
LEGACY_COURSEDIC_FILE = config.paths.root_dir / 'source-code' / 'coursedic.json'


def resolve_baseline_file(primary: Path, legacy: Path) -> Path:
    """Use the updated data baseline when present, otherwise a legacy fallback."""
    if primary.exists():
        return primary
    if legacy.exists():
        logger.warning(f"{primary} missing; falling back to legacy baseline {legacy}.")
        return legacy
    logger.error(f"No baseline found. Checked {primary} and {legacy}.")
    return primary


def load_baseline_course_numbers(path: Path) -> set[str]:
    """Read the comma-separated committed baseline of course numbers."""
    if not path.exists():
        logger.warning(f"Baseline {path} missing; treating as empty.")
        return set()
    raw = path.read_text().strip()
    if not raw:
        return set()
    return {n.strip() for n in raw.split(',') if n.strip()}


def load_current_course_numbers() -> set[str]:
    """Read the freshly produced course-numbers file from this run."""
    path = config.paths.course_numbers_file
    if not path.exists():
        logger.error(f"Expected current course numbers at {path}, but the file is missing.")
        return set()
    raw = path.read_text().strip()
    return {n.strip() for n in raw.split(',') if n.strip()}


def get_probe_limit() -> int | None:
    """Optional cap for diagnostic runs; by default, probe all active courses."""
    raw = os.getenv('CHECK_PROBE_LIMIT') or os.getenv('CHECK_SAMPLE_SIZE')
    if not raw:
        return None
    try:
        limit = int(raw)
    except ValueError:
        logger.warning(f"Invalid probe limit {raw!r}; probing all eligible courses.")
        return None
    return limit if limit > 0 else None


def max_participants(data: dict) -> int:
    """Highest participants count in stored grade entries, used for capped probes."""
    grades = data.get('grades') or []
    counts: list[int] = []
    for grade in grades:
        if not isinstance(grade, dict):
            continue
        try:
            counts.append(int(grade.get('participants') or 0))
        except (TypeError, ValueError):
            continue
    return max(counts, default=0)


def select_probe_courses(
    coursedic: dict,
    current_courses: set[str],
    limit: int | None = None,
) -> list[str]:
    """Pick current courses with baseline grades, optionally capped by activity."""
    scored: list[tuple[int, str]] = []
    for course_n, data in coursedic.items():
        if course_n not in current_courses or not (data.get('grades') or []):
            continue
        scored.append((max_participants(data), course_n))
    if limit is None:
        return sorted(course_n for _, course_n in scored)
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [course_n for _, course_n in scored[:limit]]


def existing_grade_urls(coursedic: dict, course_n: str) -> set[str]:
    """All grade-page URLs we already have stored for a given course."""
    urls: set[str] = set()
    for grade in coursedic.get(course_n, {}).get('grades', []) or []:
        url = grade.get('url')
        if url:
            urls.add(url.strip())
    return urls


def normalize_grade_href(href: str) -> str:
    """Turn a relative or absolute karakterer href into a canonical URL.

    The scheme is forced to a single canonical value per host so baseline
    URLs stored as http:// compare equal to freshly scraped https:// ones.
    """
    absolute = urljoin(f"{BASE_URL}/", href.strip())
    parsed = urlsplit(absolute)
    scheme = 'http' if parsed.netloc.lower() == 'karakterer.dtu.dk' else 'https'
    netloc = parsed.netloc.lower()
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, ''))


def is_grade_histogram_href(href: str) -> bool:
    """Return whether an href points to a DTU grade histogram page."""
    parsed = urlsplit(urljoin(f"{BASE_URL}/", href.strip()))
    return parsed.netloc.lower() == 'karakterer.dtu.dk' and bool(GRADE_PATH_RE.fullmatch(parsed.path))


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
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return course_n, set()

    soup = BeautifulSoup(html, 'lxml')
    found: set[str] = set()
    for a in soup.find_all('a'):
        href = a.get('href')
        if href and is_grade_histogram_href(href):
            found.add(normalize_grade_href(href))
    return course_n, found


async def probe_new_semesters(
    probe_courses: list[str],
    coursedic: dict,
) -> list[dict]:
    """For each probed course, return any grade URLs not in the baseline."""
    try:
        session_cookie = config.paths.secret_file.read_text().strip()
    except FileNotFoundError:
        raise RuntimeError(f"{config.paths.secret_file} missing; cannot probe semesters.")
    if not session_cookie:
        raise RuntimeError(f"{config.paths.secret_file} is empty; cannot probe semesters.")

    cookies = {'ASP.NET_SessionId': session_cookie}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept-Encoding': 'gzip, deflate',
    }
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    new_semesters: list[dict] = []
    courses_with_grade_links = 0
    async with aiohttp.ClientSession(connector=connector, cookies=cookies, headers=headers) as session:
        tasks = [fetch_grade_links_for_course(session, semaphore, c) for c in probe_courses]
        for coro in asyncio.as_completed(tasks):
            course_n, found_urls = await coro
            if found_urls:
                courses_with_grade_links += 1
            baseline = existing_grade_urls(coursedic, course_n)
            # Compare normalized — baseline urls in coursedic may be stored
            # with or without scheme; normalize both sides.
            baseline_norm = {normalize_grade_href(u) for u in baseline}
            for url in sorted(found_urls - baseline_norm):
                new_semesters.append({'course': course_n, 'url': url})
                logger.info(f"New semester for {course_n}: {url}")
    if probe_courses and courses_with_grade_links == 0:
        raise RuntimeError("No grade links found for any probed course; session cookie may be stale.")
    return sorted(new_semesters, key=lambda item: (item['course'], item['url']))


def write_report(report: dict) -> None:
    try:
        REPORT_FILE.write_text(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, TypeError) as e:
        logger.error(f"Failed to write report to {REPORT_FILE}: {e}")
        raise
    logger.info(f"Wrote report to {REPORT_FILE}")


def base_report(**overrides) -> dict:
    """Create a report with stable defaults for workflow consumers."""
    report = {
        'has_changes': False,
        'added_courses': [],
        'removed_courses': [],
        'new_semesters': [],
        'checked_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'sample_size': 0,
        'probed_course_count': 0,
        'baseline_course_count': 0,
        'current_course_count': 0,
        'course_info_base_url': f"{BASE_URL}/course",
    }
    report.update(overrides)
    return report


def main() -> int:
    logger.info("Starting weekly DTU course-data check.")

    # Read the committed baseline before refreshing data/coursenumbers.txt.
    # Legacy files are useful for count/report context, but they are stale and
    # must not drive alerts: comparing today's DTU pages against source-code/*
    # would rediscover years of already-known changes as "new".
    baseline_numbers_file = resolve_baseline_file(BASELINE_NUMBERS_FILE, LEGACY_NUMBERS_FILE)
    baseline_missing = not BASELINE_NUMBERS_FILE.exists()
    baseline = load_baseline_course_numbers(baseline_numbers_file)

    # Step 1: refresh course-number list (writes data/coursenumbers.txt).
    if not get_course_numbers():
        logger.error("Failed to fetch current course numbers; aborting.")
        write_report(base_report(check_failed=True, failure_reason='course_number_refresh_failed'))
        return 1

    current = load_current_course_numbers()
    if not current:
        logger.error("No current course numbers found after refresh; aborting.")
        write_report(base_report(check_failed=True, failure_reason='current_course_numbers_missing'))
        return 1
    if baseline_missing:
        added = []
        removed = []
        logger.error("Current course-number baseline missing; suppressing added/removed diff to avoid noisy alerts.")
    else:
        added = sorted(current - baseline)
        removed = sorted(baseline - current)
    logger.info(
        f"Course list diff: {len(added)} added, {len(removed)} removed "
        f"(baseline={len(baseline)}, current={len(current)})."
    )

    # Step 2: load coursedic.json baseline and pick courses for probing.
    new_semesters: list[dict] = []
    probe_courses: list[str] = []
    probe_error = None
    baseline_coursedic_file = resolve_baseline_file(BASELINE_COURSEDIC_FILE, LEGACY_COURSEDIC_FILE)
    coursedic_baseline_missing = not BASELINE_COURSEDIC_FILE.exists()
    if coursedic_baseline_missing:
        logger.error(
            "Current coursedic baseline missing; skipping semester probe to avoid noisy alerts from stale legacy data."
        )
    elif baseline_coursedic_file.exists():
        try:
            coursedic = json.loads(baseline_coursedic_file.read_text())
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse {baseline_coursedic_file}: {e}")
            coursedic = {}
        if coursedic:
            probe_limit = get_probe_limit()
            probe_courses = select_probe_courses(coursedic, current, probe_limit)
            if probe_limit is None:
                logger.info(f"Probing all {len(probe_courses)} current courses with baseline grades.")
            else:
                logger.info(f"Probing {len(probe_courses)} capped courses for new semesters.")
            if probe_courses:
                try:
                    new_semesters = asyncio.run(probe_new_semesters(probe_courses, coursedic))
                except Exception as e:
                    probe_error = str(e)
                    logger.error(probe_error)
    else:
        logger.warning(f"{baseline_coursedic_file} missing; skipping semester probe.")

    has_changes = bool(added or removed or new_semesters)
    report = base_report(
        has_changes=has_changes,
        added_courses=added,
        removed_courses=removed,
        new_semesters=new_semesters,
        sample_size=len(probe_courses),
        probed_course_count=len(probe_courses),
        baseline_course_count=len(baseline),
        current_course_count=len(current),
        baseline_missing=baseline_missing,
        coursedic_baseline_missing=coursedic_baseline_missing,
    )
    if probe_error:
        report['probe_error'] = probe_error
    write_report(report)

    if probe_error:
        return 1

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
