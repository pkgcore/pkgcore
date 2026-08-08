"""Read only smoke tests against the real bugs.gentoo.org.

These catch schema drift that no cassette can. Run with ``pytest --network``.
"""

import pytest

from pkgcore.bugzilla import errors
from pkgcore.bugzilla.bug import INCLUDE_FIELDS
from pkgcore.bugzilla.client import Bugzilla
from pkgcore.bugzilla.enums import OPEN_STATUSES, BugCategory, Component
from pkgcore.bugzilla.query import BugQuery
from pkgcore.bugzilla.transport import AuthMode


@pytest.fixture
def bugzilla():
    return Bugzilla()


# an ancient, public, long settled bug; bug 1 itself isn't reachable
KNOWN_BUG = 100


@pytest.mark_network
class TestLive:
    def test_get_a_bug(self, bugzilla):
        bug = bugzilla.get(KNOWN_BUG)
        assert bug.id == KNOWN_BUG
        assert bug.summary
        assert bug.creation_time.year == 2002

    def test_missing_bug(self, bugzilla):
        with pytest.raises(errors.BugzillaNotFound):
            bugzilla.get(999999999)

    def test_every_include_field_comes_back(self, bugzilla):
        raw = bugzilla.raw_search(BugQuery.component(Component.STABILIZATION).paged(1))
        assert raw, "no open stabilization bugs, which should never happen"
        missing = set(INCLUDE_FIELDS) - set(raw[0])
        assert not missing, f"bgo no longer returns {sorted(missing)}"

    def test_search_and_parse(self, bugzilla):
        bugs = bugzilla.search(
            BugQuery.category(BugCategory.STABLEREQ)
            & BugQuery.unresolved()
            & BugQuery().paged(5)
        )
        assert bugs
        for bug in bugs.values():
            assert bug.category is BugCategory.STABLEREQ
            assert not bug.resolved
            # exercises the package list parser against real content
            assert bug.package_list.atoms is not None

    def test_unresolved_matches_the_open_statuses(self, bugzilla):
        base = BugQuery.component(Component.KEYWORDING)
        fields = ("id",)
        unresolved = {
            b["id"]
            for b in bugzilla.raw_search(base & BugQuery.unresolved(), fields=fields)
        }
        open_status = {
            b["id"]
            for b in bugzilla.raw_search(
                base & BugQuery.status(*OPEN_STATUSES), fields=fields
            )
        }
        assert unresolved and unresolved == open_status

    def test_boolean_charts_filter(self, bugzilla):
        query = (
            BugQuery.component(Component.STABILIZATION)
            & BugQuery.flag("sanity-check", "+")
            & BugQuery().paged(5)
        )
        for bug in bugzilla.search(query).values():
            assert bug.sanity_check is True

    def test_anonymous_truncates_emails(self, bugzilla):
        # documents why anything matching on addresses needs an api key
        bug = bugzilla.get(KNOWN_BUG)
        assert "@" not in bug.assigned_to

    def test_whoami_needs_a_key(self, bugzilla):
        with pytest.raises(errors.BugzillaAuthError):
            bugzilla.whoami()

    def test_header_auth_is_still_unsupported(self):
        # if this ever starts passing, bgo has moved past bugzilla 5.2 and
        # AuthMode.HEADER can become the default
        client = Bugzilla("invalid-key", auth_mode=AuthMode.HEADER)
        with pytest.raises(errors.BugzillaAuthError) as excinfo:
            client.whoami()
        assert excinfo.value.code == 410, (
            "bgo now reads X-BUGZILLA-API-KEY; expected it to be ignored"
        )
