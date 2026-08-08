import urllib.error
import urllib.request

import pytest

from pkgcore.bugzilla import errors
from pkgcore.bugzilla.testing import API_KEY, Cassette, response
from pkgcore.bugzilla.transport import (
    USER_AGENT,
    AuthMode,
    UrllibTransport,
    build_user_agent,
    expect_list,
    expect_object,
    redact,
)


class TestRedact:
    def test_removes_the_key(self):
        url = "https://bugs.example.org/rest/bug?id=1&Bugzilla_api_key=secret"
        assert "secret" not in redact(url)
        assert "id=1" in redact(url)

    def test_no_query(self):
        assert redact("https://bugs.example.org/rest/bug") == (
            "https://bugs.example.org/rest/bug"
        )


class TestRequests:
    def test_get(self, cassette):
        handler, transport = cassette(response({"bugs": []}))
        assert transport.request("GET", "bug", params=(("id", "1"),)) == {"bugs": []}
        (call,) = handler.calls
        assert call.method == "GET"
        assert call.path == "/rest/bug"
        assert ("id", "1") in call.query
        assert call.body is None

    def test_leading_slash_is_tolerated(self, cassette):
        handler, transport = cassette(response({}))
        transport.request("GET", "/bug/1")
        assert handler.calls[0].path == "/rest/bug/1"

    def test_headers(self, cassette):
        handler, transport = cassette(response({}))
        transport.request("GET", "bug")
        headers = handler.calls[0].headers
        assert headers["Accept"] == "application/json"
        assert headers["User-agent"] == USER_AGENT
        assert "Content-type" not in headers

    def test_custom_user_agent(self, cassette):
        handler, transport = cassette(response({}), user_agent="gentoo/1.2")
        transport.request("GET", "bug")
        agent = handler.calls[0].header("user-agent")
        assert agent == f"gentoo/1.2 {USER_AGENT}"

    def test_put_body(self, cassette):
        handler, transport = cassette(response({"bugs": []}))
        transport.request("PUT", "bug/1", body={"ids": [1], "summary": "x"})
        (call,) = handler.calls
        assert call.method == "PUT"
        assert call.headers["Content-type"] == "application/json"
        assert call.body["ids"] == [1]

    def test_post_body(self, cassette):
        handler, transport = cassette(response({"id": 5}))
        assert transport.request("POST", "bug", body={"summary": "x"}) == {"id": 5}
        assert handler.calls[0].method == "POST"


class TestAuth:
    def test_key_in_query_for_reads(self, cassette):
        handler, transport = cassette(response({}))
        transport.request("GET", "bug")
        assert ("Bugzilla_api_key", API_KEY) in handler.calls[0].query
        assert "X-bugzilla-api-key" not in handler.calls[0].headers

    def test_key_in_body_for_writes(self, cassette):
        handler, transport = cassette(response({}))
        transport.request("PUT", "bug/1", body={"ids": [1]})
        (call,) = handler.calls
        assert call.body["Bugzilla_api_key"] == API_KEY
        assert "Bugzilla_api_key" not in dict(call.query)

    def test_header_mode(self, cassette):
        handler, transport = cassette(response({}), auth_mode=AuthMode.HEADER)
        transport.request("GET", "bug")
        (call,) = handler.calls
        assert call.headers["X-bugzilla-api-key"] == API_KEY
        assert "Bugzilla_api_key" not in dict(call.query)

    def test_anonymous_reads(self, cassette):
        handler, transport = cassette(response({"bugs": []}), api_key=None)
        transport.request("GET", "bug")
        assert "Bugzilla_api_key" not in dict(handler.calls[0].query)
        assert not transport.authenticated

    def test_anonymous_writes_fail_without_a_round_trip(self, cassette):
        handler, transport = cassette(api_key=None)
        with pytest.raises(errors.BugzillaAuthRequired, match="anonymous"):
            transport.request("PUT", "bug/1", body={"ids": [1]})
        assert handler.calls == []


class TestUserAgent:
    def test_default(self):
        assert build_user_agent() == USER_AGENT

    def test_client_token_comes_first(self):
        assert build_user_agent("glibc/1.0") == f"glibc/1.0 {USER_AGENT}"

    def test_blank_client_is_ignored(self):
        assert build_user_agent("") == USER_AGENT


class TestErrors:
    def test_error_body_with_a_2xx_status(self, cassette):
        # bugzilla does this, so the body has to win over the status
        _, transport = cassette(
            response({"error": True, "code": 101, "message": "Bug #1 does not exist."})
        )
        with pytest.raises(errors.BugzillaNotFound) as excinfo:
            transport.request("GET", "bug/1")
        assert excinfo.value.code == 101

    def test_invalid_api_key_arrives_as_400(self, cassette):
        _, transport = cassette(
            response(
                {"error": True, "code": 306, "message": "The API key is invalid."},
                status=400,
            )
        )
        with pytest.raises(errors.BugzillaAuthError) as excinfo:
            transport.request("GET", "bug/1")
        assert (excinfo.value.code, excinfo.value.status) == (306, 400)

    def test_login_required_arrives_as_401(self, cassette):
        _, transport = cassette(
            response({"error": True, "code": 410, "message": "log in"}, status=401)
        )
        with pytest.raises(errors.BugzillaAuthError):
            transport.request("GET", "whoami")

    def test_permission_denied(self, cassette):
        _, transport = cassette(
            response({"error": True, "code": 102, "message": "nope"}, status=401)
        )
        with pytest.raises(errors.BugzillaPermissionDenied):
            transport.request("GET", "bug/1")

    def test_unknown_code_stays_generic(self, cassette):
        _, transport = cassette(
            response({"error": True, "code": 999, "message": "?"}, status=400)
        )
        with pytest.raises(errors.BugzillaResponseError) as excinfo:
            transport.request("GET", "bug/1")
        assert type(excinfo.value) is errors.BugzillaResponseError

    def test_html_body(self, cassette):
        _, transport = cassette(
            response(raw=b"<html>blocked</html>", content_type="text/html")
        )
        with pytest.raises(errors.BugzillaProtocolError, match="isn't JSON"):
            transport.request("GET", "bug/1")

    def test_failing_status_without_an_error_body(self, cassette):
        _, transport = cassette(response({"unexpected": True}, status=404))
        with pytest.raises(errors.BugzillaNotFound):
            transport.request("GET", "bug/1")

    def test_api_key_is_redacted_from_messages(self, cassette):
        _, transport = cassette(
            response({"error": True, "code": 101, "message": "nope"})
        )
        with pytest.raises(errors.BugzillaNotFound) as excinfo:
            transport.request("GET", "bug/1")
        assert API_KEY not in excinfo.value.url
        assert API_KEY not in str(excinfo.value)

    def test_connection_error(self):
        class Broken(urllib.request.HTTPSHandler):
            def https_open(self, req):
                raise urllib.error.URLError("connection reset by peer")

            http_open = https_open

        transport = UrllibTransport(
            "https://bugs.example.org",
            API_KEY,
            retries=1,
            opener=urllib.request.build_opener(Broken()),
        )
        with pytest.raises(errors.BugzillaConnectionError, match="reset by peer"):
            transport.request("GET", "bug/1")


class TestRetries:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr("pkgcore.bugzilla.transport.time.sleep", lambda _: None)

    def test_reads_are_retried(self, cassette):
        handler, transport = cassette(
            response(raw=b"", status=503),
            response(raw=b"", status=503),
            response({"bugs": []}),
            retries=3,
        )
        assert transport.request("GET", "bug") == {"bugs": []}
        assert len(handler.calls) == 3

    def test_retries_are_bounded(self, cassette):
        handler, transport = cassette(
            *(response(raw=b"", status=503) for _ in range(3)), retries=3
        )
        with pytest.raises(errors.BugzillaServerError):
            transport.request("GET", "bug")
        assert len(handler.calls) == 3

    def test_writes_are_not_retried(self, cassette):
        # a retried bug creation would file a duplicate
        handler, transport = cassette(response(raw=b"", status=503), retries=3)
        with pytest.raises(errors.BugzillaServerError):
            transport.request("POST", "bug", body={"summary": "x"})
        assert len(handler.calls) == 1

    def test_writes_retry_when_asked(self, cassette):
        handler, transport = cassette(
            response(raw=b"", status=503),
            response({"id": 5}),
            retries=3,
            retry_writes=True,
        )
        assert transport.request("POST", "bug", body={"summary": "x"}) == {"id": 5}
        assert len(handler.calls) == 2

    def test_client_errors_are_not_retried(self, cassette):
        handler, transport = cassette(
            response({"error": True, "code": 101, "message": "nope"}, status=404),
            retries=3,
        )
        with pytest.raises(errors.BugzillaNotFound):
            transport.request("GET", "bug/1")
        assert len(handler.calls) == 1

    def test_connection_errors_are_retried(self, monkeypatch):
        attempts = []

        class Flaky(urllib.request.HTTPSHandler):
            def https_open(self, req):
                attempts.append(req)
                if len(attempts) < 3:
                    raise urllib.error.URLError("reset")
                return Cassette().expect_bugs().opener.open(req)

            http_open = https_open

        transport = UrllibTransport(
            "https://bugs.example.org",
            API_KEY,
            retries=3,
            opener=urllib.request.build_opener(Flaky()),
        )
        assert transport.request("GET", "bug") == {"bugs": []}
        assert len(attempts) == 3


class TestShapeGuards:
    def test_expect_object(self):
        assert expect_object({"a": 1}, "ctx") == {"a": 1}

    def test_expect_object_rejects_a_list(self):
        with pytest.raises(errors.BugzillaSchemaError, match="expected an object"):
            expect_object([], "ctx")

    def test_expect_list(self):
        assert expect_list({"bugs": [1]}, "bugs", "ctx") == [1]

    def test_expect_list_missing_key(self):
        with pytest.raises(errors.BugzillaSchemaError, match="'bugs' list"):
            expect_list({}, "bugs", "ctx")

    def test_expect_list_wrong_type(self):
        with pytest.raises(errors.BugzillaSchemaError):
            expect_list({"bugs": {}}, "bugs", "ctx")
