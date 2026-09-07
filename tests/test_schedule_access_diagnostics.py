import json

import pytest

from dtu_analyzer.scripts import diagnose_schedule_access as diagnostic


COOKIE = {'name': 'ASP.NET_SessionId', 'value': 'PRIVATE_COOKIE_VALUE', 'domain': 'kurser.dtu.dk',
          'path': '/', 'secure': True, 'httpOnly': True, 'sameSite': 'Lax'}
COURSE_HTML = '<h2>01001 Mathematics</h2><table><tr><td>Schedule</td><td>Autumn</td></tr></table>'


def test_cookie_metadata_never_contains_values():
    metadata = diagnostic.cookie_metadata([COOKIE])
    assert metadata[0]['name'] == 'ASP.NET_SessionId'
    assert 'value' not in metadata[0]
    assert COOKIE['value'] not in json.dumps(metadata)


def test_login_page_does_not_export_content_or_query_secrets():
    result = diagnostic.inspect_page('<input value="PASSWORD">', 'https://auth.dtu.dk/login?token=SECRET')
    assert result['login_page']
    assert result['schedule'] == {}
    assert 'SECRET' not in json.dumps(result)
    assert 'PASSWORD' not in json.dumps(result)


class Response:
    def __init__(self, url, status=200, body='', headers=None):
        self.url, self.status, self.body = url, status, body
        self.headers = headers or {}
        self.disposed = False

    def text(self):
        return self.body

    def dispose(self):
        self.disposed = True


class Context:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.request = self
        self.urls = []

    def get(self, url, **kwargs):
        assert kwargs['max_redirects'] == 0
        self.urls.append(url)
        return next(self.responses)


def test_full_cookie_request_follows_wrapper_and_records_redirects():
    url = 'https://kurser.dtu.dk/course/01001?lang=en-GB'
    responses = [
        Response(url, body='<iframe src="?forceLogin=true"></iframe>'),
        Response(url, 302, headers={'location': '/course/01001?lang=en-GB'}),
        Response(url, body=COURSE_HTML),
    ]
    context = Context(responses)
    result = diagnostic.request_probe(context, url)
    assert result['schedule_found']
    assert 'forceLogin=true' in context.urls[1]
    assert [a['status'] for a in result['attempts']] == [200, 302, 200]
    assert all(response.disposed for response in responses)


def test_redirect_does_not_send_full_auth_state_outside_dtu():
    url = 'https://kurser.dtu.dk/course/01001'
    context = Context([Response(url, 302, headers={'location': 'https://example.com/?token=SECRET'})])
    result = diagnostic.request_probe(context, url)
    assert result['error'] == 'redirect_outside_dtu_https'
    assert len(context.urls) == 1
    assert 'SECRET' not in json.dumps(result)


@pytest.mark.parametrize('flags,expected', [
    ((True, True, True, True), 'all_modes_succeeded_failure_not_reproduced'),
    ((True, True, True, False), 'user_agent_difference_candidate'),
    ((True, True, False, False), 'full_cookie_state_or_http_client_difference_candidate'),
    ((True, False, False, False), 'browser_navigation_or_storage_required_candidate'),
    ((False, False, False, False), 'no_mode_recovered_schedule_check_login_and_course_availability'),
])
def test_comparison_interpretations_are_hypotheses(flags, expected):
    modes = {mode: {'schedule_found': flag} for mode, flag in zip(diagnostic.MODES, flags)}
    assert diagnostic.interpret(modes) == expected


def test_transport_error_is_not_interpreted_as_missing_cookie_evidence():
    modes = {mode: {'schedule_found': True} for mode in diagnostic.MODES}
    modes['session_cookie_browser_agent'] = {'schedule_found': False, 'error': 'TimeoutError'}
    assert diagnostic.interpret(modes) == 'comparison_incomplete_check_errors'


def test_auth_failure_still_produces_an_artifact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('AUTH_DIAGNOSTIC_COURSES', '01001,01020')
    monkeypatch.setattr(diagnostic, 'authenticate', lambda **kwargs: False)
    assert diagnostic.main() == 1
    report = json.loads((tmp_path / 'exam-classification-report/auth-report.json').read_text())
    assert report['error'] == 'authentication_failed_before_comparison'
    assert set(report['courses']) == {'01001', '01020'}


def test_comparison_uses_isolated_state_and_does_not_persist_it(monkeypatch, tmp_path):
    snapshot = {'cookies': [COOKIE], 'origins': [{'origin': 'https://kurser.dtu.dk',
                'localStorage': [{'name': 'private', 'value': 'PRIVATE_STORAGE_VALUE'}]}]}

    class Page:
        url = 'https://kurser.dtu.dk/?token=PRIVATE_TOKEN'

        def evaluate(self, expression):
            return 'Browser-Agent'

    class Login:
        pages = [Page()]

        def storage_state(self):
            return snapshot

    class Isolated:
        def close(self):
            pass

    class Browser:
        contexts = []

        def new_context(self, **kwargs):
            assert kwargs['storage_state'] == snapshot
            self.contexts.append(Isolated())
            return self.contexts[-1]

    browser = Browser()
    monkeypatch.setattr(diagnostic, 'browser_probe', lambda *args: {'schedule_found': True})
    monkeypatch.setattr(diagnostic, 'request_probe', lambda *args: {'schedule_found': True})
    agents = []

    async def probe(url, cookie, agent):
        assert cookie == COOKIE['value']
        agents.append(agent)
        return {'schedule_found': True}

    monkeypatch.setattr(diagnostic, 'session_probe', probe)
    report = {'courses': {'01001': {}}}
    diagnostic.compare_access(browser, Login(), COOKIE['value'], report, tmp_path)
    assert len(browser.contexts) == 2 and browser.contexts[0] is not browser.contexts[1]
    assert agents == ['Browser-Agent', diagnostic.DIAGNOSTIC_USER_AGENT]
    saved = (tmp_path / 'auth-report.json').read_text()
    assert 'PRIVATE_' not in saved
    assert report['courses']['01001']['interpretation'] == 'all_modes_succeeded_failure_not_reproduced'
