"""Coverage for the replay helpers other projects are meant to reuse."""

import pytest

from pkgcore.bugzilla import errors, transport
from pkgcore.bugzilla.changes import NewBug
from pkgcore.bugzilla.client import Bugzilla
from pkgcore.bugzilla.enums import Component
from pkgcore.bugzilla.testing import Cassette, response


def new_bug(summary="cat/pkg-1: stablereq"):
    return NewBug(
        summary=summary, description="please", component=Component.STABILIZATION
    )


class TestCassette:
    def test_expect_bugs(self):
        cassette = Cassette().expect_bugs({"id": 1}, {"id": 2})
        assert sorted(cassette.client().search()) == [1, 2]

    def test_expect_created(self):
        cassette = Cassette().expect_created(900123)
        assert cassette.client().create(new_bug()) == 900123

    def test_expect_changed(self):
        cassette = Cassette().expect_changed(
            5, status={"added": "RESOLVED", "removed": "CONFIRMED"}
        )
        from pkgcore.bugzilla.changes import BugUpdate

        changes = cassette.client().update(5, BugUpdate.resolve(comment="done"))
        assert changes.changes["status"].added == ("RESOLVED",)

    def test_expect_error(self):
        cassette = Cassette().expect_error(101, "no such bug", status=404)
        with pytest.raises(errors.BugzillaNotFound):
            cassette.client().search()

    def test_expect_whoami(self):
        cassette = Cassette().expect_whoami(name="someone@gentoo.org")
        assert cassette.client().whoami().name == "someone@gentoo.org"

    def test_chaining(self):
        cassette = Cassette().expect_whoami().expect_bugs({"id": 1})
        client = cassette.client()
        client.whoami()
        assert list(client.search()) == [1]
        cassette.assert_drained()

    def test_recordings_may_be_passed_to_the_constructor(self):
        cassette = Cassette(response({"bugs": [{"id": 3}]}))
        assert list(cassette.client().search()) == [3]

    def test_intercepts_plain_http(self):
        cassette = Cassette(base_url="http://bugs.example.org").expect_bugs({"id": 1})
        assert list(cassette.client().search()) == [1]
        assert cassette.calls[0].url.startswith("http://")

    def test_unexpected_request(self):
        with pytest.raises(AssertionError, match="unexpected request"):
            Cassette().client().search()

    def test_assert_drained(self):
        cassette = Cassette().expect_bugs()
        with pytest.raises(AssertionError, match="unused recordings"):
            cassette.assert_drained()

    def test_anonymous_client(self):
        cassette = Cassette(api_key=None).expect_bugs()
        assert not cassette.client().search()
        assert "Bugzilla_api_key" not in cassette.calls[0].params


class TestCall:
    def test_inspection(self):
        cassette = Cassette().expect_created(1)
        cassette.client().create(new_bug("cat/pkg-1: stablereq"))
        (call,) = cassette.calls
        assert call.method == "POST"
        assert call.path == "/rest/bug"
        assert call.body["summary"] == "cat/pkg-1: stablereq"
        assert call.header("content-type") == "application/json"
        assert call.header("Content-Type") == "application/json"
        assert call.header("no-such-header") is None

    def test_params_group_repeated_keys(self):
        from pkgcore.bugzilla.query import BugQuery

        cassette = Cassette().expect_bugs()
        cassette.client().search(BugQuery.ids((1, 2, 3)))
        assert cassette.calls[0].params["id"] == ["1", "2", "3"]


class TestDynamicResponses:
    def test_callable_body_sees_the_call(self):
        cassette = Cassette().always(
            response(lambda call: {"id": len(call.body["summary"])})
        )
        assert cassette.client().create(new_bug("abcde")) == 5

    def test_creates_bugs_answers_every_filing(self):
        cassette = Cassette().creates_bugs()
        client = cassette.client()
        assert [client.create(new_bug()) for _ in range(3)] == [1, 2, 3]

    def test_fallback_only_applies_once_the_queue_is_empty(self):
        cassette = Cassette().expect_created(100).creates_bugs(first=7)
        client = cassette.client()
        assert [client.create(new_bug()) for _ in range(2)] == [100, 7]


class TestGlobalInstall:
    """The path downstream CLI tests need, where the client is out of reach"""

    def build_a_client_somewhere_unreachable(self):
        return Bugzilla("some-key", base_url="https://bugs.example.org")

    def test_context_manager_intercepts_clients_it_did_not_build(self):
        with Cassette().expect_created(42) as cassette:
            bug_id = self.build_a_client_somewhere_unreachable().create(new_bug())
        assert bug_id == 42
        assert cassette.calls[0].path == "/rest/bug"

    def test_the_opener_is_restored_afterwards(self):
        original = transport.build_opener
        with Cassette().creates_bugs():
            assert transport.build_opener is not original
        assert transport.build_opener is original

    def test_restored_even_when_the_body_raises(self):
        original = transport.build_opener
        with pytest.raises(ValueError), Cassette():
            raise ValueError("boom")
        assert transport.build_opener is original

    def test_fixture_installs_by_default(self, bugzilla_cassette):
        # the plugin fixture is already active, so no opener needs passing
        bugzilla_cassette.expect_created(7)
        assert self.build_a_client_somewhere_unreachable().create(new_bug()) == 7
