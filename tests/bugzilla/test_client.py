import pytest

from pkgcore.bugzilla import errors
from pkgcore.bugzilla.changes import BugUpdate, ListChange, NewBug
from pkgcore.bugzilla.client import PAGE_SIZE
from pkgcore.bugzilla.enums import BugCategory, Component, FlagStatus, Resolution
from pkgcore.bugzilla.query import BugQuery
from pkgcore.bugzilla.testing import API_KEY, response

WHOAMI = response({"id": 7, "name": "dev@gentoo.org", "real_name": "A Dev"})


def raw_bug(bug_id, **kwargs):
    return {
        "id": bug_id,
        "product": "Gentoo Linux",
        "component": "Stabilization",
        "resolution": "",
        "summary": f"bug {bug_id}",
        "cc": [],
        "keywords": [],
        "depends_on": [],
        "blocks": [],
        "flags": [],
        "alias": [],
        "cf_stabilisation_atoms": "",
        "cf_runtime_testing_required": "---",
        "last_change_time": "2024-01-02T03:04:05Z",
        "creation_time": "2024-01-01T00:00:00Z",
        **kwargs,
    }


def raw_comment(comment_id, bug_id, creator, tags=(), text="hi"):
    return {
        "id": comment_id,
        "bug_id": bug_id,
        "count": comment_id,
        "text": text,
        "creator": creator,
        "time": "2024-01-01T00:00:00Z",
        "creation_time": "2024-01-01T00:00:00Z",
        "is_private": False,
        "tags": list(tags),
    }


class TestWhoami:
    def test_whoami(self, client):
        handler, bz = client(WHOAMI)
        user = bz.whoami()
        assert user.name == "dev@gentoo.org"
        assert handler.calls[0].path == "/rest/whoami"

    def test_cached(self, client):
        handler, bz = client(WHOAMI)
        assert bz.whoami() is bz.whoami()
        assert len(handler.calls) == 1


class TestGet:
    def test_single(self, client):
        handler, bz = client(response({"bugs": [raw_bug(900001)]}))
        bug = bz.get(900001)
        assert bug.id == 900001
        assert bug.category is BugCategory.STABLEREQ
        assert ("id", "900001") in handler.calls[0].query

    def test_single_missing(self, client):
        _, bz = client(response({"bugs": []}))
        with pytest.raises(errors.BugzillaNotFound, match="900001"):
            bz.get(900001)

    def test_several(self, client):
        _, bz = client(response({"bugs": [raw_bug(1), raw_bug(2)]}))
        bugs = bz.get([1, 2])
        assert sorted(bugs) == [1, 2]
        assert bugs[1].summary == "bug 1"

    def test_several_tolerates_missing(self, client):
        _, bz = client(response({"bugs": [raw_bug(1)]}))
        assert list(bz.get([1, 2])) == [1]


class TestSearch:
    def test_include_fields_is_always_sent(self, client):
        handler, bz = client(response({"bugs": []}))
        bz.search(BugQuery.unresolved())
        fields = dict(handler.calls[0].query)["include_fields"]
        assert "cf_stabilisation_atoms" in fields
        assert "id" in fields

    def test_query_params_are_forwarded(self, client):
        handler, bz = client(response({"bugs": []}))
        bz.search(
            BugQuery.component(Component.STABILIZATION)
            & BugQuery.flag("sanity-check", FlagStatus.GRANTED)
        )
        query = handler.calls[0].query
        assert ("component", "Stabilization") in query
        assert ("f1", "flagtypes.name") in query
        assert ("v1", "sanity-check+") in query

    def test_paging_stops_on_a_short_page(self, client):
        handler, bz = client(response({"bugs": [raw_bug(1)]}))
        assert list(bz.search()) == [1]
        assert len(handler.calls) == 1
        assert ("limit", str(PAGE_SIZE)) in handler.calls[0].query

    def test_paging_follows_full_pages(self, client):
        handler, bz = client(
            response({"bugs": [raw_bug(i) for i in range(PAGE_SIZE)]}),
            response({"bugs": [raw_bug(PAGE_SIZE)]}),
        )
        assert len(bz.search()) == PAGE_SIZE + 1
        assert len(handler.calls) == 2
        assert ("offset", str(PAGE_SIZE)) in handler.calls[1].query

    def test_explicit_limit_is_honoured(self, client):
        handler, bz = client(response({"bugs": [raw_bug(1), raw_bug(2)]}))
        assert len(bz.search(BugQuery().paged(2))) == 2
        assert ("limit", "2") in handler.calls[0].query
        assert len(handler.calls) == 1

    def test_batching_splits_long_id_lists(self, client):
        ids = list(range(900000, 903000))
        handler, bz = client(
            *(
                response({"bugs": []})
                for _ in BugQuery.ids(ids).batches(base_length=500)
            )
        )
        bz.search(BugQuery.ids(ids))
        assert len(handler.calls) > 1
        seen = [v for call in handler.calls for k, v in call.query if k == "id"]
        assert sorted(map(int, seen)) == ids

    def test_raw_search_narrow_projection(self, client):
        handler, bz = client(response({"bugs": [{"id": 1, "summary": "s"}]}))
        raw = bz.raw_search(BugQuery.unresolved(), fields=("id", "summary"))
        assert raw == ({"id": 1, "summary": "s"},)
        assert dict(handler.calls[0].query)["include_fields"] == "id,summary"

    def test_malformed_response(self, client):
        _, bz = client(response({"unexpected": 1}))
        with pytest.raises(errors.BugzillaSchemaError, match="'bugs' list"):
            bz.search()


class TestResolveDependencies:
    def test_transitive_closure(self, client):
        _, bz = client(
            response({"bugs": [raw_bug(2, depends_on=[3])]}),
            response({"bugs": [raw_bug(3)]}),
        )
        start = {1: bz.get(2)}
        resolved = bz.resolve_dependencies({2: start[1]})
        assert sorted(resolved) == [2, 3]

    def test_nothing_to_do(self, client):
        handler, bz = client(response({"bugs": [raw_bug(1)]}))
        bugs = bz.get([1])
        assert bz.resolve_dependencies(bugs) == bugs
        assert len(handler.calls) == 1

    def test_unreachable_dependency_is_dropped(self, client, caplog):
        # a deleted or security restricted dep must not spin forever
        _, bz = client(
            response({"bugs": [raw_bug(1, depends_on=[999])]}),
            response({"bugs": []}),
        )
        bugs = bz.get([1])
        assert list(bz.resolve_dependencies(bugs)) == [1]
        assert "unreachable bug dependencies" in caplog.text

    def test_input_is_not_mutated(self, client):
        _, bz = client(
            response({"bugs": [raw_bug(1, depends_on=[2])]}),
            response({"bugs": [raw_bug(2)]}),
        )
        bugs = bz.get([1])
        bz.resolve_dependencies(bugs)
        assert list(bugs) == [1]


class TestComments:
    def test_comments(self, client):
        _, bz = client(
            response(
                {
                    "bugs": {
                        "5": {
                            "comments": [
                                raw_comment(1, 5, "a@gentoo.org"),
                                raw_comment(2, 5, "b@gentoo.org"),
                            ]
                        }
                    },
                    "comments": {},
                }
            )
        )
        comments = bz.comments(5)
        assert [x.id for x in comments] == [1, 2]

    def test_missing_bug_key(self, client):
        _, bz = client(response({"bugs": {}, "comments": {}}))
        with pytest.raises(errors.BugzillaSchemaError, match="no entry for bug 5"):
            bz.comments(5)

    def test_latest_comment_defaults_to_the_current_user(self, client):
        _, bz = client(
            WHOAMI,
            response(
                {
                    "bugs": {
                        "5": {
                            "comments": [
                                raw_comment(1, 5, "dev@gentoo.org", text="old"),
                                raw_comment(2, 5, "other@gentoo.org"),
                                raw_comment(3, 5, "dev@gentoo.org", text="new"),
                            ]
                        }
                    },
                    "comments": {},
                }
            ),
        )
        assert bz.latest_comment(5).text == "new"

    def test_latest_comment_for_another_creator(self, client):
        _, bz = client(
            response(
                {
                    "bugs": {"5": {"comments": [raw_comment(1, 5, "a@gentoo.org")]}},
                    "comments": {},
                }
            )
        )
        assert bz.latest_comment(5, creator="a@gentoo.org").id == 1

    def test_latest_comment_when_there_is_none(self, client):
        _, bz = client(
            response(
                {
                    "bugs": {"5": {"comments": [raw_comment(1, 5, "a@gentoo.org")]}},
                    "comments": {},
                }
            )
        )
        assert bz.latest_comment(5, creator="nobody@gentoo.org") is None


class TestCreate:
    def test_create(self, client):
        handler, bz = client(response({"id": 900123}))
        bug = NewBug(
            summary="dev-libs/a: stablereq",
            description="please",
            component=Component.STABILIZATION,
        )
        assert bz.create(bug) == 900123
        (call,) = handler.calls
        assert call.method == "POST"
        assert call.path == "/rest/bug"
        assert call.body["summary"] == "dev-libs/a: stablereq"
        assert call.body["Bugzilla_api_key"] == API_KEY

    def test_missing_id_in_response(self, client):
        _, bz = client(response({}))
        bug = NewBug(summary="s", description="d", component=Component.ECLASSES)
        with pytest.raises(errors.BugzillaSchemaError, match="no id in response"):
            bz.create(bug)

    def test_anonymous_client_cannot_create(self, client):
        handler, bz = client(api_key=None)
        bug = NewBug(summary="s", description="d", component=Component.ECLASSES)
        with pytest.raises(errors.BugzillaAuthRequired):
            bz.create(bug)
        assert handler.calls == []

    def test_not_retried(self, client, monkeypatch):
        monkeypatch.setattr("pkgcore.bugzilla.transport.time.sleep", lambda _: None)
        handler, bz = client(response(raw=b"", status=503), retries=3)
        bug = NewBug(summary="s", description="d", component=Component.ECLASSES)
        with pytest.raises(errors.BugzillaServerError):
            bz.create(bug)
        assert len(handler.calls) == 1


class TestUpdate:
    CHANGED = response(
        {
            "bugs": [
                {
                    "id": 5,
                    "alias": [],
                    "last_change_time": "2024-01-02T03:04:05Z",
                    "changes": {
                        "status": {"added": "RESOLVED", "removed": "CONFIRMED"}
                    },
                }
            ]
        }
    )

    def test_single(self, client):
        handler, bz = client(self.CHANGED)
        changes = bz.update(5, BugUpdate.resolve(comment="done"))
        assert changes.id == 5
        assert changes.changes["status"].added == ("RESOLVED",)
        (call,) = handler.calls
        assert call.method == "PUT"
        assert call.path == "/rest/bug/5"
        assert call.body["ids"] == [5]

    def test_several_send_the_full_id_list(self, client):
        # the body overrides the path id, so a partial list would lose bugs
        handler, bz = client(self.CHANGED)
        result = bz.update([5, 6, 7], BugUpdate(summary="x"))
        assert isinstance(result, tuple)
        (call,) = handler.calls
        assert call.path == "/rest/bug/5"
        assert call.body["ids"] == [5, 6, 7]

    def test_needs_ids(self, client):
        _, bz = client()
        with pytest.raises(errors.BugzillaUsageError, match="at least one bug id"):
            bz.update([], BugUpdate(summary="x"))

    def test_obsoleting(self, client):
        handler, bz = client(self.CHANGED)
        bz.update(5, BugUpdate.obsoleted_by(900999))
        assert handler.calls[0].body["resolution"] == Resolution.OBSOLETE
        assert handler.calls[0].body["see_also"] == {
            "add": ["https://bugs.gentoo.org/900999"]
        }

    def test_sanity_check(self, client):
        handler, bz = client(self.CHANGED)
        bz.update(
            5, BugUpdate.sanity_check(True, cc=ListChange.adding("amd64@gentoo.org"))
        )
        body = handler.calls[0].body
        assert body["flags"] == [{"name": "sanity-check", "status": "+"}]
        assert body["cc"] == {"add": ["amd64@gentoo.org"]}


class TestCommentTags:
    def test_tag_comments(self, client):
        handler, bz = client(response(["obsolete"]), response(["obsolete"]))
        bz.tag_comments([11, 12], ListChange.adding("obsolete"))
        assert [x.path for x in handler.calls] == [
            "/rest/bug/comment/11/tags",
            "/rest/bug/comment/12/tags",
        ]
        assert handler.calls[0].body["add"] == ["obsolete"]

    def test_mark_own_comments_obsolete(self, client):
        handler, bz = client(
            WHOAMI,
            response(
                {
                    "bugs": {
                        "5": {
                            "comments": [
                                raw_comment(1, 5, "dev@gentoo.org"),
                                raw_comment(2, 5, "other@gentoo.org"),
                                raw_comment(3, 5, "dev@gentoo.org", tags=["obsolete"]),
                            ]
                        }
                    },
                    "comments": {},
                }
            ),
            response(["obsolete"]),
        )
        assert bz.mark_own_comments_obsolete(5) == 1
        assert handler.calls[-1].path == "/rest/bug/comment/1/tags"

    def test_nothing_to_obsolete(self, client):
        handler, bz = client(
            WHOAMI,
            response(
                {
                    "bugs": {
                        "5": {"comments": [raw_comment(1, 5, "other@gentoo.org")]}
                    },
                    "comments": {},
                }
            ),
        )
        assert bz.mark_own_comments_obsolete(5) == 0
        assert len(handler.calls) == 2
