import asyncio

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
