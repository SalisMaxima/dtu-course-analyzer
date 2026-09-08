"""Compare course-info discovery in an authenticated browser and the scraper.

Persist only bounded structural evidence and sanitized request metadata.
Authentication state and response bodies stay in memory.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookies import SimpleCookie
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from yarl import URL

from .probe_exam_classification import (
    BROWSER_USER_AGENT, extract_histogram_links, fetch_page, info_evidence,
)


def inspect_info(html, url, course):
    evidence = info_evidence(html, url, course)
    # Never extract links from authentication content.
    links = [] if evidence["state"] == "authentication_required_or_expired" else extract_histogram_links(html, course)
    return {**evidence, "histograms": links}


def network_url(url):
    """Only course-service metadata; never auth hosts, queries or fragments."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"kurser.dtu.dk", "karakterer.dtu.dk"}:
        return None
    if re.search(r"login|auth|token|password|session|callback", parsed.path, re.I):
        return None
    if len(parsed.path) > 256 or any(len(segment) > 64 for segment in parsed.path.split("/")):
        return None
    return urlunsplit(("https", parsed.hostname, parsed.path, "", ""))


async def direct_probe(course, cookie):
    url = f"https://kurser.dtu.dk/course/{course}/info?lang=en-GB"
    jar = aiohttp.CookieJar()
    scoped = SimpleCookie()
    scoped["ASP.NET_SessionId"] = cookie
    scoped["ASP.NET_SessionId"]["secure"] = True
    jar.update_cookies(scoped, response_url=URL("https://kurser.dtu.dk"))
    diagnostics = {}
    try:
        async with aiohttp.ClientSession(cookie_jar=jar, headers={"User-Agent": BROWSER_USER_AGENT}) as session:
            html = await fetch_page(session, url, diagnostics)
        return {**inspect_info(html, url, course), "requests": diagnostics}
    except Exception as exc:
        # fetch_page uses fixed error codes; don't persist exception text.
        return {"state": "access_or_loading_failure", "error": type(exc).__name__, "requests": diagnostics}


def browser_probe(context, course):
    page = context.new_page()
    requests, failures = [], []
    url = f"https://kurser.dtu.dk/course/{course}/info?lang=en-GB"

    def record_response(response):
        target = network_url(response.url)
        if target and response.request.resource_type in {"document", "xhr", "fetch"} and len(requests) < 80:
            requests.append({"url": target, "status": response.status,
                             "resource_type": response.request.resource_type})

    def record_failure(request):
        target = network_url(request.url)
        if target and request.resource_type in {"document", "xhr", "fetch"} and len(failures) < 20:
            failures.append({"url": target, "resource_type": request.resource_type})

    page.on("response", record_response)
    page.on("requestfailed", record_failure)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Fixed observation window allows delayed DOM/frame/API results to appear.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            page.wait_for_timeout(250)
        if not network_url(page.url):
            return {"state": "access_or_loading_failure", "error": "unexpected_navigation",
                    "network": requests, "failed_requests": failures}
        frames = []
        for frame in page.frames[:20]:
            target = network_url(frame.url)
            if target is None:
                continue
            try:
                frames.append({"url": target, **inspect_info(frame.content(), frame.url, course)})
            except Exception as exc:
                frames.append({"url": target, "state": "access_or_loading_failure", "error": type(exc).__name__})
        links = {e["url"]: e for frame in frames for e in frame.get("histograms", [])}
        states = {frame["state"] for frame in frames}
        failed = bool(failures or any(r["status"] >= 400 for r in requests)
                      or states & {"access_or_loading_failure", "authentication_required_or_expired"})
        state = ("links_found" if links else "access_or_loading_failure" if failed else
                 "no_published_results" if "no_published_results" in states else "no_links_unknown")
        return {"state": state, "histograms": list(links.values()), "frames": frames,
                "network": requests, "failed_requests": failures, "loading_failures": failed,
                "observation_seconds": 10}
    except Exception as exc:
        return {"state": "access_or_loading_failure", "error": type(exc).__name__,
                "network": requests, "failed_requests": failures}
    finally:
        page.close()


def interpret(direct, browser):
    a = {e["url"] for e in direct.get("histograms", [])}
    b = {e["url"] for e in browser.get("histograms", [])}
    failed = any(v.get("error") or v.get("loading_failures") or v.get("state") in {
        "access_or_loading_failure", "authentication_required_or_expired"} for v in (direct, browser))
    if failed:
        outcome = "access_or_loading_failure"
    elif a and a == b:
        outcome = "links_present_in_both"
    elif b - a:
        outcome = "additional_links_in_browser" if a else "links_only_in_browser"
    elif a - b:
        outcome = "links_missing_in_browser"
    elif direct.get("state") == browser.get("state") == "no_published_results":
        outcome = "explicitly_empty_history"
    else:
        outcome = "unresolved"
    return {"outcome": outcome, "browser_only_links": sorted(b - a), "direct_only_links": sorted(a - b)}


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    temp = output / "info-report.json.tmp"
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output / "info-report.json")
    lines = ["# Course-info browser comparison", "",
             "Browser/direct differences are evidence, not proof of a JavaScript or authentication cause.", "",
             "| Course | Direct links | Browser links | Outcome |", "| --- | --- | --- | --- |"]
    for course, row in report["courses"].items():
        lines.append(f"| {course} | {len(row.get('direct', {}).get('histograms', []))} | "
                     f"{len(row.get('browser', {}).get('histograms', []))} | "
                     f"{row.get('comparison', {}).get('outcome', 'not_run')} |")
    if report.get("error"):
        lines.extend(["", f"Diagnostic error: {report['error']}"])
    (output / "info-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_info_access(browser, login_context, cookie, report, output):
    snapshot = login_context.storage_state()
    agent = login_context.pages[0].evaluate("navigator.userAgent")
    for course, row in report["courses"].items():
        with ThreadPoolExecutor(max_workers=1) as executor:
            row["direct"] = executor.submit(lambda: asyncio.run(direct_probe(course, cookie))).result()
        write_report(report, output)
        context = None
        try:
            context = browser.new_context(storage_state=snapshot, user_agent=agent)
            row["browser"] = browser_probe(context, course)
        except Exception as exc:
            row["browser"] = {"state": "access_or_loading_failure", "error": type(exc).__name__}
        finally:
            if context is not None:
                context.close()
        row["comparison"] = interpret(row["direct"], row["browser"])
        write_report(report, output)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_report(report, output)
