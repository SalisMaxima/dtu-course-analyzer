import asyncio
import json
from types import SimpleNamespace

import pytest

from dtu_analyzer.analysis.exam_classification import classify_course, schedule_from_text
from dtu_analyzer.scripts import diagnose_info_access as info
from dtu_analyzer.scripts import probe_exam_classification as probe

LINK = "https://karakterer.dtu.dk/Histogram/1/02285/Summer-2026"
HTML = f'<h2>02280 Grade history</h2><a href="{LINK}">02285 s26</a>'


@pytest.mark.parametrize("course,target", [("02281", "02285"), ("02427", "02424"),
                                          ("23105", "23102"), ("23106", "23102")])
def test_other_course_reference_is_retained_but_unassigned(course, target):
    html = f'<a href="https://karakterer.dtu.dk/Histogram/1/{target}/Summer-2026">{target}</a>'
    exams = probe.extract_histogram_links(html, course)
    exams[0].update(distribution_status="published", grades={"participants": 10, "7": "10"})
    row = classify_course({"course": course, "schedule": schedule_from_text("Spring"), "exams": exams})
    assert row["status"] == "undetermined"
    assert row["primary_exam"] is None
    assert row["resit_exams"] == []
    assert row["exams"][0]["histogram_course"] == target
    assert row["exams"][0]["grades"]["7"] == "10"
    assert row["exams"][0]["reason"] == "different_course_identity_unverified"


def result(state, links=()):
    return {"state": state, "histograms": [{"url": url} for url in links]}


@pytest.mark.parametrize("direct,browser,outcome", [
    (result("links_found", [LINK]), result("links_found", [LINK]), "links_present_in_both"),
    (result("no_links_unknown"), result("links_found", [LINK]), "links_only_in_browser"),
    (result("links_found", [LINK]), result("no_links_unknown"), "links_missing_in_browser"),
    (result("no_published_results"), result("no_published_results"), "explicitly_empty_history"),
    (result("no_links_unknown"), result("no_published_results"), "unresolved"),
    (result("no_links_unknown"), result("no_links_unknown"), "unresolved"),
    (result("access_or_loading_failure"), result("links_found", [LINK]), "access_or_loading_failure"),
])
def test_comparison_does_not_invent_empty_history_or_javascript_cause(direct, browser, outcome):
    assert info.interpret(direct, browser)["outcome"] == outcome


def test_evidence_does_not_record_credentials_or_login_content():
    assert info.network_url("https://auth.dtu.dk/login?token=secret") is None
    assert info.network_url("https://kurser.dtu.dk/api/token/secret") is None
    assert info.network_url("https://kurser.dtu.dk/api/grades?token=secret#secret") == "https://kurser.dtu.dk/api/grades"
    page = info.inspect_info('<form><input type="password" value="secret"></form>' + HTML,
                             "https://kurser.dtu.dk/course/02280/info", "02280")
    assert page["histograms"] == []
    assert "secret" not in json.dumps(page)


def test_browser_collects_delayed_frame_links_and_network_metadata(monkeypatch):
    class Frame:
        url = "https://kurser.dtu.dk/course/02280/info?forceLogin=true"
        def content(self):
            return HTML
    class Page:
        url = "https://kurser.dtu.dk/course/02280/info"
        frames = [Frame()]
        handlers = {}
        waited = False
        closed = False
        def on(self, event, callback):
            self.handlers[event] = callback
        def goto(self, *args, **kwargs):
            self.handlers["response"](SimpleNamespace(url="https://kurser.dtu.dk/api/grades?token=SECRET",
                 status=200, request=SimpleNamespace(resource_type="xhr")))
        def wait_for_timeout(self, duration):
            self.waited = True
        def close(self):
            self.closed = True
    page = Page()
    times = iter([0, 0, 11])
    monkeypatch.setattr(info.time, "monotonic", lambda: next(times))
    result = info.browser_probe(SimpleNamespace(new_page=lambda: page), "02280")
    assert page.waited and page.closed
    assert result["histograms"][0]["url"] == LINK
    assert result["frames"][0]["histograms"][0]["identity_status"] == "different_course_requires_review"
    assert result["network"][0]["url"] == "https://kurser.dtu.dk/api/grades"
    assert "SECRET" not in json.dumps(result)


@pytest.mark.asyncio
async def test_direct_probe_uses_scraper_cookie_scope_and_records_failure(monkeypatch):
    async def fetch(session, url, diagnostics):
        assert session.headers["User-Agent"] == probe.BROWSER_USER_AGENT
        assert session.cookie_jar.filter_cookies(probe.URL("https://kurser.dtu.dk"))
        assert not session.cookie_jar.filter_cookies(probe.URL("https://karakterer.dtu.dk"))
        assert not session.cookie_jar.filter_cookies(probe.URL("http://kurser.dtu.dk"))
        return HTML
    monkeypatch.setattr(info, "fetch_page", fetch)
    result = await info.direct_probe("02280", "SECRET")
    assert result["histograms"][0]["url"] == LINK
    assert "SECRET" not in json.dumps(result)
    async def broken(*args):
        raise ValueError("SECRET")
    monkeypatch.setattr(info, "fetch_page", broken)
    result = await info.direct_probe("02280", "SECRET")
    assert result["state"] == "access_or_loading_failure"
    assert "SECRET" not in json.dumps(result)


def test_comparison_context_is_isolated_and_checkpointed(monkeypatch, tmp_path):
    snapshot = {"cookies": [{"value": "SECRET"}]}
    contexts = []
    class Context:
        closed = False
        def close(self):
            self.closed = True
    class Browser:
        def new_context(self, **kwargs):
            assert kwargs["storage_state"] == snapshot
            c = Context()
            contexts.append(c)
            return c
    login = SimpleNamespace(storage_state=lambda: snapshot,
                            pages=[SimpleNamespace(evaluate=lambda code: "Browser-Agent")])
    async def direct(*args):
        return result("links_found", [LINK])
    monkeypatch.setattr(info, "direct_probe", direct)
    monkeypatch.setattr(info, "browser_probe", lambda *args: result("links_found", [LINK]))
    report = {"courses": {"02280": {}, "02426": {}}}
    info.compare_info_access(Browser(), login, "SECRET", report, tmp_path)
    assert len(contexts) == 2 and all(c.closed for c in contexts)
    saved = (tmp_path / "info-report.json").read_text()
    assert "SECRET" not in saved
    assert report["courses"]["02280"]["comparison"]["outcome"] == "links_present_in_both"
    assert len((tmp_path / "info-summary.md").read_text().splitlines()) > 5


@pytest.mark.asyncio
async def test_shared_history_is_attached_to_each_source_without_aggregation(monkeypatch):
    async def fetch(session, url, diagnostics=None):
        if "/Histogram/" in url:
            return "<h2>23102 Grade history</h2><table>Fordelingen vises ikke da tre eller færre</table>"
        if "/info" in url:
            return '<a href="https://karakterer.dtu.dk/Histogram/1/23102/Summer-2026">23102</a>'
        return "<h2>Current course</h2><table><tr><td>Schedule</td><td>Spring</td></tr></table>"
    monkeypatch.setattr(probe, "fetch_page", fetch)
    a = await probe.collect_course(None, asyncio.Semaphore(1), "23103")
    b = await probe.collect_course(None, asyncio.Semaphore(1), "23104")
    assert a["course"] != b["course"]
    assert len(a["exams"]) == len(b["exams"]) == 1
    assert a["exams"][0] is not b["exams"][0]
    assert a["exams"][0]["distribution_status"] == "suppressed"
    assert a["exams"][0]["histogram_title"] == "23102 Grade history"
    assert a["primary_exam"]["url"] == b["primary_exam"]["url"]
    assert a["primary_exam"] is not b["primary_exam"]
    assert a["primary_exam"]["identity_status"] == "manually_approved_history"


def test_login_callback_runs_both_experiments_and_auth_failure_is_reported(monkeypatch, tmp_path):
    from dtu_analyzer.scripts import diagnose_schedule_access as schedule
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTH_DIAGNOSTIC_COURSES", "01001")
    monkeypatch.setenv("INFO_DIAGNOSTIC_COURSES", "02280,02426")
    calls = []
    monkeypatch.setattr(schedule, "compare_access", lambda *args: calls.append("schedule"))
    monkeypatch.setattr(info, "compare_info_access", lambda *args: calls.append("info"))
    def authenticate(after_login):
        after_login(None, None, "SECRET")
        return True
    monkeypatch.setattr(schedule, "authenticate", authenticate)
    assert schedule.main() == 0
    assert calls == ["schedule", "info"]
    monkeypatch.setattr(schedule, "authenticate", lambda **kwargs: False)
    assert schedule.main() == 1
    report = json.loads((tmp_path / "exam-classification-report/info-report.json").read_text())
    assert report["error"] == "authentication_failed_before_comparison"
    assert set(report["courses"]) == {"02280", "02426"}


def test_different_course_csv_and_summary_keep_reference_review_visible(tmp_path):
    links = probe.extract_histogram_links(HTML, "02281")
    links[0].update(distribution_status="suppressed", grades=None)
    row = classify_course({"course": "02281", "schedule": schedule_from_text("Spring"), "exams": links})
    report = {"courses": {"02280": row}}
    probe.write_reports(report, tmp_path)
    assert report["different_course_histograms"] == 1
    assert report["variant_histograms"] == 0
    import csv
    with (tmp_path / "courses.csv").open() as stream:
        values = next(csv.DictReader(stream))
    assert json.loads(values["different_course_urls"]) == [LINK]
    assert "Different-course histograms requiring identity review: 1" in (tmp_path / "summary.md").read_text()
