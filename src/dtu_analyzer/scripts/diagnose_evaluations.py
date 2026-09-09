"""Read-only per-link evaluation diagnostics; never save full pages or cookies."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

import aiohttp
from bs4 import BeautifulSoup

from ..parsers.review_parser import parse_reviews
from .probe_exam_classification import fetch_page, diagnostic_url, BROWSER_USER_AGENT


def inspect_evaluation(html, url):
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one('input[type="password"]'):
        return {"state": "authentication_required"}
    container = soup.find("div", id="CourseResultsPublicContainer")
    table = container.find("table") if container else None
    rows = table.find_all("tr") if table else []
    cells = rows[1].find_all("td") if len(rows) > 1 else []
    participant_text = cells[0].get_text(" ", strip=True) if cells else None
    parsed = parse_reviews(html, url)
    return {
        "state": "parsed" if parsed else "parser_returned_none",
        "public_container_found": container is not None,
        "participants_table_rows": len(rows),
        "participants_row_cells": len(cells),
        "participants_cell": participant_text if participant_text is None or re.fullmatch(r"[\d\s.,]+", participant_text) else "non_numeric_text",
        "question_container_count": len(soup.select(".ResultCourseModelWrapper")),
        "parsed_participants": parsed.get("participants") if parsed else None,
        "parsed_question_ids": sorted(str(k) for k, v in (parsed or {}).items() if isinstance(v, dict)),
        "recognized_scoring_direction": (parsed or {}).get("firstOption") in {"Helt enig", "Helt uenig"},
    }


async def diagnose(course, urls):
    result = {"course": course, "observed_at": datetime.now(timezone.utc).isoformat(),
              "access": "anonymous; no stored credentials", "info": {}, "evaluations": []}
    async with aiohttp.ClientSession(headers={"User-Agent": BROWSER_USER_AGENT}) as session:
        if not urls:
            info_url = f"https://kurser.dtu.dk/course/{course}/info?lang=en-GB"
            try:
                html = await fetch_page(session, info_url, result["info"])
                urls = [urljoin(info_url, a["href"]) for a in BeautifulSoup(html, "lxml").select('a[href]')
                        if urlsplit(urljoin(info_url, a["href"])).hostname == "evaluering.dtu.dk"]
            except ValueError as exc:
                result["info"]["error"] = str(exc)
        for url in dict.fromkeys(urls):
            row = {"url": diagnostic_url(url)}
            try:
                html = await fetch_page(session, url)  # No raw page/header evidence saved.
                row.update(inspect_evaluation(html, url))
            except ValueError as exc:
                row.update(state="fetch_failed", error=str(exc))
            result["evaluations"].append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course", default="01002")
    parser.add_argument("--evaluation-url", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Z0-9]{5}", args.course):
        parser.error("Expected a five-character course ID")
    for url in args.evaluation_url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "evaluering.dtu.dk" or not re.fullmatch(r"/kursus/[A-Z0-9]{5}/\d+", parsed.path) or parsed.query or parsed.fragment:
            parser.error("Expected a public HTTPS evaluering.dtu.dk/kursus/COURSE/ID URL")
    if args.output.exists():
        parser.error("Output already exists; choose a new report filename")
    result = asyncio.run(diagnose(args.course, args.evaluation_url))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(bool(result["info"].get("error")) or not result["evaluations"]
               or any(e["state"] != "parsed" for e in result["evaluations"]))


if __name__ == "__main__":
    raise SystemExit(main())
