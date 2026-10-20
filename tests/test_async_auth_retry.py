import asyncio
import json

import pytest

from dtu_analyzer.scrapers import async_scraper as scraper


class Response:
    def __init__(self, html="<h2>Public results</h2>", status=200, url="https://kurser.dtu.dk/course/01002/info"):
        self.html, self.status, self.url = html, status, url
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        return self.html


class Session:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        response = self.responses[url].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    async def noop(*args):
        pass
    monkeypatch.setattr(scraper, "pace_request", noop)
    monkeypatch.setattr(scraper.asyncio, "sleep", noop)
    monkeypatch.setattr(scraper, "timeout_occurred", False)
    monkeypatch.setattr(scraper, "auth_failed", False)
    monkeypatch.setattr(scraper, "timeout_url", None)
    monkeypatch.setattr(scraper, "MAX_RETRIES", 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("html,final_url", [
    ('<iframe src="?forceLogin=true"></iframe>', 'https://kurser.dtu.dk/course/01002/info'),
    ('<input type="password">', 'https://evaluering.dtu.dk/kursus/01002/361313'),
    ('<html>Sign in</html>', 'https://sts.ait.dtu.dk/adfs/ls/'),
])
async def test_authentication_response_retries_original_url_once(html, final_url):
    url = "https://kurser.dtu.dk/course/01002/info"
    session = Session({url: [Response(html, url=final_url), Response("recovered")]})
    assert await scraper.fetch_url(session, url) == "recovered"
    assert session.calls == [url, url]
    assert not scraper.auth_failed


@pytest.mark.asyncio
async def test_persistent_wrapper_stops_collection_and_never_returns_empty_page():
    url = "https://kurser.dtu.dk/course/01002/info"
    wrapper = '<iframe src="?forceLogin=true"></iframe>'
    session = Session({url: [Response(wrapper), Response(wrapper)]})
    assert await scraper.fetch_url(session, url) is None
    assert scraper.auth_failed
    assert await scraper.fetch_url(session, url) is None
    assert session.calls == [url, url]


@pytest.mark.asyncio
async def test_http_retry_budget_remains_independent(monkeypatch):
    monkeypatch.setattr(scraper, "MAX_RETRIES", 1)
    url = "https://kurser.dtu.dk/course/01002/info"
    session = Session({url: [Response(status=503), Response('<input type="password">'),
                             Response(status=503), Response("recovered")]})
    assert await scraper.fetch_url(session, url) == "recovered"
    assert len(session.calls) == 4
    assert not scraper.auth_failed


@pytest.mark.asyncio
async def test_404_is_not_retried_as_an_authentication_failure():
    url = "https://kurser.dtu.dk/course/01002/info"
    session = Session({url: [Response(status=404)]})
    assert await scraper.fetch_url(session, url) is None
    assert len(session.calls) == 1 and not scraper.auth_failed


@pytest.mark.asyncio
async def test_timeout_still_sets_fatal_flag_and_raises():
    url = "https://kurser.dtu.dk/course/01002/info"
    session = Session({url: [asyncio.TimeoutError()]})
    with pytest.raises(scraper.TimeoutException):
        await scraper.fetch_url(session, url)
    assert scraper.timeout_occurred and len(session.calls) == 1


@pytest.mark.asyncio
async def test_course_collection_recovers_wrapper_and_collects_all_three_evaluations():
    url = f"{scraper.BASE_URL}/course/01002/info"
    links = [f"https://evaluering.dtu.dk/kursus/01002/{i}" for i in (361313, 332754, 311114)]
    overview = ''.join(f'<a href="{link}">Evaluation</a>' for link in links)
    responses = {url: [Response('<iframe src="?forceLogin=true"></iframe>', url=url), Response(overview, url=url)]}
    for link, participants in zip(links, (371, 386, 419)):
        html = f'<div id="CourseResultsPublicContainer"><h2>F26</h2><table><tr><th>Responses</th></tr><tr><td>{participants}</td></tr></table></div>'
        responses[link] = [Response(html, url=link)]
    # Exercise recovery on an individual evaluation as well as the overview.
    responses[links[0]].insert(0, Response('<input type="password">', url=links[0]))
    for language in ("da", "en"):
        name_url = f"{scraper.BASE_URL}/course/01002?lang={'da-DK' if language == 'da' else 'en-GB'}"
        responses[name_url] = [Response('<h2>01002 Mathematics</h2>', url=name_url)]
    result = await scraper.process_single_course(Session(responses), asyncio.Semaphore(1), "01002")
    assert result[0] == "01002"
    assert [r["participants"] for r in result[1]["reviews"]] == [371, 386, 419]
    assert not scraper.auth_failed


def course_result(course, grades=(), reviews=(), links=None, **fields):
    """A process_single_course result; links default to the collected URLs."""
    data = {**fields}
    if grades:
        data["grades"] = [{"url": u, "participants": 10} for u in grades]
    if reviews:
        data["reviews"] = [{"url": u, "participants": 10} for u in reviews]
    return (course, data, links or {"grades": list(grades), "reviews": list(reviews)})


@pytest.fixture
def scrape_dir(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/coursenumbers.txt").write_text("01001,01002,01003")
    (tmp_path / "secret.txt").write_text("cookie")
    monkeypatch.setattr(scraper.config.paths, "root_dir", tmp_path)
    monkeypatch.delenv("RESUME", raising=False)
    return tmp_path


def fake_attempts(monkeypatch, attempts):
    """Serve each course's queued results in order and record the calls."""
    calls = []

    async def fake_course(session, semaphore, course):
        calls.append(course)
        result = attempts[course].pop(0)
        return await result() if callable(result) else result
    monkeypatch.setattr(scraper, "process_single_course", fake_course)
    return calls


@pytest.mark.asyncio
async def test_courses_dropped_by_a_transient_error_are_retried_at_the_end(scrape_dir, monkeypatch):
    links = {"grades": ["g26", "g25"], "reviews": ["e26", "e25"]}
    calls = fake_attempts(monkeypatch, {
        # Dropped entirely on the first pass (the 41468 failure mode)
        "01001": [None, course_result("01001", reviews=["e26"])],
        # The retry gets the other evaluation but loses grades and names
        "01002": [course_result("01002", grades=["g26", "g25"], reviews=["e25"], links=links, name="Kursus"),
                  course_result("01002", reviews=["e26"], links=links)],
        # A retry that collects nothing keeps the earlier data
        "01003": [course_result("01003", reviews=["e26"], links=links), None],
    })

    assert await scraper.main_async() == 0
    assert sorted(calls) == ["01001", "01001", "01002", "01002", "01003", "01003"]
    data = json.loads((scrape_dir / "data/coursedic.json").read_text())
    assert [r["url"] for r in data["01001"]["reviews"]] == ["e26"]
    # Merged by URL in overview-page order (newest first), keeping fields the retry lacked
    assert [r["url"] for r in data["01002"]["reviews"]] == ["e26", "e25"]
    assert [r["url"] for r in data["01002"]["grades"]] == ["g26", "g25"]
    assert data["01002"]["name"] == "Kursus"
    assert [r["url"] for r in data["01003"]["reviews"]] == ["e26"]


def test_merge_keeps_records_from_both_passes():
    previous = {"name": "Kursus", "reviews": [{"url": "A", "n": 1}, {"url": "B", "n": 1}]}
    retry = {"reviews": [{"url": "B", "n": 2}, {"url": "C", "n": 2}]}
    merged = scraper.merge_course_data(previous, retry, {"grades": [], "reviews": ["C", "B", "A"]})
    assert merged == {"name": "Kursus", "reviews": [{"url": "C", "n": 2}, {"url": "B", "n": 2}, {"url": "A", "n": 1}]}


@pytest.mark.asyncio
async def test_resume_collects_courses_an_aborted_run_left_incomplete(scrape_dir, monkeypatch):
    links = {"grades": [], "reviews": ["e26", "e25"]}
    # Expire the session only once the main loop has recorded 01001 and 01002
    recorded = []
    both_recorded = asyncio.Event()
    merge = scraper.merge_course_data

    def recording_merge(*args):
        recorded.append(args)
        if len(recorded) == 2:
            both_recorded.set()
        return merge(*args)
    monkeypatch.setattr(scraper, "merge_course_data", recording_merge)

    async def expire_session():
        await both_recorded.wait()
        scraper.auth_failed = True
        return None
    calls = fake_attempts(monkeypatch, {
        "01001": [course_result("01001", reviews=["e26"])],
        "01002": [course_result("01002", reviews=["e26"], links=links),
                  course_result("01002", reviews=["e26", "e25"], links=links)],
        "01003": [expire_session, course_result("01003", reviews=["e26"])],
    })

    assert await scraper.main_async() == 1
    assert len(recorded) == 2
    checkpoint = json.loads((scrape_dir / "data/coursedic.partial.json").read_text())
    assert set(checkpoint) == {"01001"}

    monkeypatch.setattr(scraper, "auth_failed", False)
    monkeypatch.setenv("RESUME", "1")
    calls.clear()
    assert await scraper.main_async() == 0
    assert sorted(calls) == ["01002", "01003"]
    data = json.loads((scrape_dir / "data/coursedic.json").read_text())
    assert [r["url"] for r in data["01002"]["reviews"]] == ["e26", "e25"]
