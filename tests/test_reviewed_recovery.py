import asyncio
import json
from pathlib import Path

import pytest

from tests.test_exam_classification import Response, Session
from tests.test_maintainer_pipeline import report
from dtu_analyzer.scripts import probe_exam_classification as probe
from dtu_analyzer.scripts.build_chrome_beta import build_dataset
from dtu_analyzer.analysis.publication_guard import publication_issues


@pytest.mark.asyncio
async def test_login_wrapper_failure_retries_original_public_url(monkeypatch):
    async def no_wait(*args):
        pass
    monkeypatch.setattr(probe.asyncio, "sleep", no_wait)
    url = "https://kurser.dtu.dk/course/12601?lang=en-GB"
    session = Session([Response(html='<iframe src="?forceLogin=true"></iframe>', url=url),
                       Response(url="https://auth.dtu.dk/login"), Response(html="public", url=url)])
    requested = []
    get = session.get
    def track(url, **kwargs):
        requested.append(url)
        return get(url, **kwargs)
    session.get = track
    assert await probe.fetch_page(session, url) == "public"
    assert requested[0] == requested[2] == url
    assert "forceLogin=true" in requested[1]


def test_reviewed_404_is_excluded_but_other_errors_still_block():
    evidence = report("22461", [("22433", "Summer-2023"), ("22433", "Winter-2023")])
    bad = evidence["courses"]["22461"]["exams"][0]
    bad.update(error="HTTP 404", distribution_status="failed", grades=None)
    evidence["courses"]["22461"] = probe.classify_course(evidence["courses"]["22461"])
    data = build_dataset({}, [evidence])
    assert len(data["22461"]["exam_history"]) == 1
    assert data["22461"]["default_exam_id"].endswith("Winter-2023")
    assert not publication_issues({}, data, evidence, ["22461"])
    bad = evidence["courses"]["22461"]["exams"][0]
    bad["error"] = "network_error_or_timeout"
    assert publication_issues({}, data, evidence, ["22461"])


def test_22181_uses_reviewed_winter_despite_current_spring_schedule():
    data = build_dataset({}, [report("22181", [("22180", "Winter-2025"), ("22180", "Summer-2024")], "Spring")])
    assert data["22181"]["default_exam_id"].endswith("Winter-2025")


@pytest.mark.asyncio
async def test_missing_previously_collected_suppressed_exam_is_refetched(monkeypatch):
    urls = []
    async def fetch(session, url, diagnostics=None):
        urls.append(url)
        if "/Histogram/" in url:
            return "<p>Fordelingen vises ikke da tre eller færre har været til denne eksamen.</p>"
        if "/info" in url:
            return '<p>25205</p><a href="https://karakterer.dtu.dk/Histogram/1/25205/Summer-2026">s26</a>'
        return '<h2>25205</h2><table><tr><td>Schedule</td><td>Spring</td></tr></table>'
    monkeypatch.setattr(probe, "fetch_page", fetch)
    row = await probe.collect_course(None, asyncio.Semaphore(1), "25205")
    assert len(row["exams"]) == 2
    assert any(u.endswith("Summer-2022") for u in urls)
    assert all(e["distribution_status"] == "suppressed" and not e.get("grades") for e in row["exams"])
