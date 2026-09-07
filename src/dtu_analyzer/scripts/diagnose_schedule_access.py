"""Compare course access immediately after login on the Actions runner.

Authentication state is copied in memory to isolate each comparison. Only
cookie metadata and structural page evidence are written to artifacts.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit

import aiohttp
from yarl import URL

from ..auth.authenticator import authenticate
from ..analysis.exam_classification import extract_schedule
from ..scrapers.async_scraper import is_login_page
from .probe_exam_classification import course_wrapper_url, diagnostic_url


DIAGNOSTIC_USER_AGENT = 'DTU-Course-Analyzer/diagnostic'
MODES = ('browser', 'full_cookie_request', 'session_cookie_browser_agent',
         'session_cookie_diagnostic_agent')


def cookie_metadata(cookies):
    keys = ('name', 'domain', 'path', 'secure', 'httpOnly', 'sameSite')
    return [{key: cookie.get(key) for key in keys} for cookie in cookies]


def inspect_page(html, url):
    login = is_login_page(html, url)
    schedule = {} if login else extract_schedule(html)
    return {'final_url': diagnostic_url(url), 'login_page': login,
            'wrapper': bool(course_wrapper_url(html, url)) if not login else False,
            'schedule_found': bool(schedule.get('raw')), 'schedule': schedule}


def allowed_destination(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and (host == 'dtu.dk' or host.endswith('.dtu.dk'))


def request_probe(context, url):
    """Follow redirects explicitly to capture where full-cookie requests go."""
    attempts = []
    wrapper_followed = False
    try:
        for _ in range(10):
            if not allowed_destination(url):
                return {'schedule_found': False, 'error': 'redirect_outside_dtu_https', 'attempts': attempts}
            response = context.request.get(url, max_redirects=0, timeout=15000)
            try:
                attempts.append({'url': diagnostic_url(response.url), 'status': response.status})
                if response.status in (301, 302, 303, 307, 308) and response.headers.get('location'):
                    url = urljoin(response.url, response.headers['location'])
                    continue
                html = response.text()
                result = inspect_page(html, response.url)
                target = course_wrapper_url(html, response.url)
                if target and not wrapper_followed:
                    wrapper_followed, url = True, target
                    continue
                return {**result, 'attempts': attempts}
            finally:
                response.dispose()
        return {'schedule_found': False, 'error': 'redirect_limit', 'attempts': attempts}
    except Exception as exc:
        return {'schedule_found': False, 'error': type(exc).__name__, 'attempts': attempts}


async def session_probe(url, cookie, user_agent):
    """Match the diagnostic's host-only secure cookie with controlled agents."""
    jar = aiohttp.CookieJar()
    scoped = SimpleCookie()
    scoped['ASP.NET_SessionId'] = cookie
    scoped['ASP.NET_SessionId']['secure'] = True
    jar.update_cookies(scoped, response_url=URL('https://kurser.dtu.dk'))
    attempts = []
    wrapper_followed = False
    try:
        async with aiohttp.ClientSession(cookie_jar=jar, headers={'User-Agent': user_agent}) as session:
            for _ in range(10):
                if not allowed_destination(url):
                    return {'schedule_found': False, 'error': 'redirect_outside_dtu_https', 'attempts': attempts}
                async with session.get(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    attempts.append({'url': diagnostic_url(str(response.url)), 'status': response.status})
                    if response.status in (301, 302, 303, 307, 308) and response.headers.get('Location'):
                        url = urljoin(str(response.url), response.headers['Location'])
                        continue
                    html = await response.text()
                    result = inspect_page(html, str(response.url))
                    target = course_wrapper_url(html, str(response.url))
                    if target and not wrapper_followed:
                        wrapper_followed, url = True, target
                        continue
                    return {**result, 'attempts': attempts}
            return {'schedule_found': False, 'error': 'redirect_limit', 'attempts': attempts}
    except Exception as exc:
        return {'schedule_found': False, 'error': type(exc).__name__, 'attempts': attempts}


def browser_probe(context, url):
    page = context.new_page()
    navigations = []
    page.on('response', lambda response: navigations.append({
        'url': diagnostic_url(response.url), 'status': response.status
    }) if response.request.is_navigation_request() else None)
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        deadline = time.monotonic() + 10
        frames = []
        while True:
            frames = [inspect_page(frame.content(), frame.url) for frame in page.frames
                      if frame.url.startswith('https://')]
            if any(frame['schedule_found'] for frame in frames) or time.monotonic() >= deadline:
                break
            page.wait_for_timeout(250)
        return {'schedule_found': any(frame['schedule_found'] for frame in frames),
                'frames': frames, 'attempts': navigations,
                'cookie_metadata_after': cookie_metadata(context.cookies())}
    except Exception as exc:
        return {'schedule_found': False, 'error': type(exc).__name__, 'attempts': navigations}
    finally:
        page.close()


def interpret(modes):
    if not all(mode in modes and 'error' not in modes[mode] for mode in MODES):
        return 'comparison_incomplete_check_errors'
    ok = {mode: bool(modes[mode].get('schedule_found')) for mode in MODES}
    if all(ok.values()):
        return 'all_modes_succeeded_failure_not_reproduced'
    if ok['session_cookie_browser_agent'] and not ok['session_cookie_diagnostic_agent']:
        return 'user_agent_difference_candidate'
    if ok['full_cookie_request'] and not ok['session_cookie_browser_agent']:
        return 'full_cookie_state_or_http_client_difference_candidate'
    if ok['browser'] and not ok['full_cookie_request']:
        return 'browser_navigation_or_storage_required_candidate'
    if not any(ok.values()):
        return 'no_mode_recovered_schedule_check_login_and_course_availability'
    return 'mixed_results_inspect_attempts'


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'auth-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    lines = ['# Schedule-access authentication diagnostic', '',
             'Comparisons are diagnostic hypotheses, not automatic authentication fixes.', '',
             '| Course | Browser | Full cookies | Session / browser agent | Session / diagnostic agent |',
             '| --- | --- | --- | --- | --- |']
    for course, row in report['courses'].items():
        cells = [('error' if 'error' in row.get(mode, {}) else
                  'schedule found' if row.get(mode, {}).get('schedule_found') else
                  'no schedule' if mode in row else 'not run') for mode in MODES]
        lines.append('| ' + ' | '.join([course, *cells]) + ' |')
    lines.append('')
    for course, row in report['courses'].items():
        if row.get('interpretation'):
            lines.append(f"- {course}: {row['interpretation']}")
    if report.get('error'):
        lines.extend(['', f"Diagnostic error: {report['error']}"])
    (output / 'auth-summary.md').write_text('\n'.join(lines) + '\n')


def compare_access(browser, login_context, cookie, report, output):
    # Never persist the state: it contains live authentication credentials.
    snapshot = login_context.storage_state()
    user_agent = login_context.pages[0].evaluate('navigator.userAgent')
    report.update(cookie_metadata=cookie_metadata(snapshot['cookies']),
                  browser_user_agent=user_agent, diagnostic_user_agent=DIAGNOSTIC_USER_AGENT,
                  login_url=diagnostic_url(login_context.pages[0].url))
    write_report(report, output)
    for course, modes in report['courses'].items():
        url = f'https://kurser.dtu.dk/course/{course}?lang=en-GB'
        for mode in MODES:
            try:
                if mode in ('browser', 'full_cookie_request'):
                    context = browser.new_context(storage_state=snapshot, user_agent=user_agent)
                    try:
                        modes[mode] = browser_probe(context, url) if mode == 'browser' else request_probe(context, url)
                    finally:
                        context.close()
                else:
                    agent = user_agent if mode == 'session_cookie_browser_agent' else DIAGNOSTIC_USER_AGENT
                    # Playwright's sync API owns an event loop; isolate aiohttp's loop.
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        modes[mode] = executor.submit(lambda: asyncio.run(session_probe(url, cookie, agent))).result()
            except Exception as exc:
                modes[mode] = {'schedule_found': False, 'error': type(exc).__name__}
            write_report(report, output)
        modes['interpretation'] = interpret(modes)
        write_report(report, output)


def main():
    output = Path('exam-classification-report')
    courses = sorted(set(filter(None, re.split(r'[,\s]+', os.getenv('AUTH_DIAGNOSTIC_COURSES', '01001,01020').strip()))))
    report = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'courses': {course: {} for course in courses}}
    if not courses or len(courses) > 7 or any(not re.fullmatch(r'[0-9A-Z]{5}', c) for c in courses):
        report.update(error='provide_one_to_seven_valid_course_ids', courses={})
        write_report(report, output)
        return 1
    write_report(report, output)

    def after_login(browser, context, cookie):
        try:
            compare_access(browser, context, cookie, report, output)
        except Exception as exc:
            report['error'] = type(exc).__name__
            write_report(report, output)

    authenticated = authenticate(after_login=after_login)
    if not authenticated:
        report['error'] = 'authentication_failed_before_comparison'
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_report(report, output)
    return 0 if authenticated else 1


if __name__ == '__main__':
    raise SystemExit(main())
