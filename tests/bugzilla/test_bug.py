import dataclasses
import datetime

import pytest

from pkgcore.bugzilla.bug import (
    INCLUDE_FIELDS,
    Bug,
    Flag,
    parse_bug,
    parse_changes,
    parse_comment,
    parse_user,
)
from pkgcore.bugzilla.enums import BugCategory, FlagStatus, RuntimeTesting
from pkgcore.bugzilla.errors import PackageListError
from pkgcore.ebuild.atom import atom

RAW_BUG = {
    "id": 900001,
    "summary": "dev-libs/a: stablereq",
    "product": "Gentoo Linux",
    "component": "Stabilization",
    "version": "unspecified",
    "status": "CONFIRMED",
    "resolution": "",
    "severity": "enhancement",
    "priority": "Normal",
    "assigned_to": "maint@gentoo.org",
    "creator": "reporter@gentoo.org",
    "cc": ["amd64@gentoo.org", "x86@gentoo.org", "someone@example.com"],
    "keywords": ["CC-ARCHES"],
    "whiteboard": "",
    "alias": [],
    "tags": [],
    "depends_on": [900000],
    "blocks": [899999],
    "see_also": [],
    "groups": [],
    "flags": [
        {
            "id": 51984,
            "name": "sanity-check",
            "status": "+",
            "type_id": 6,
            "setter": "nattka@gentoo.org",
            "creation_date": "2024-01-02T03:04:05Z",
            "modification_date": "2024-01-02T03:04:05Z",
        }
    ],
    "deadline": None,
    "creation_time": "2024-01-01T00:00:00Z",
    "last_change_time": "2024-01-02T03:04:05Z",
    "cf_stabilisation_atoms": "=dev-libs/a-1.2 amd64 x86\r\n",
    "cf_runtime_testing_required": "---",
}


class TestIncludeFields:
    def test_matches_declared_fields(self):
        declared = {
            field.metadata["wire"]
            for field in dataclasses.fields(Bug)
            if "wire" in field.metadata
        }
        assert set(INCLUDE_FIELDS) == declared

    def test_every_field_is_declared(self):
        assert all("wire" in field.metadata for field in dataclasses.fields(Bug)), (
            "a Bug field without a wire name is never populated"
        )

    def test_no_duplicates(self):
        assert len(INCLUDE_FIELDS) == len(set(INCLUDE_FIELDS))


class TestParseBug:
    @pytest.fixture
    def bug(self):
        return parse_bug(RAW_BUG)

    def test_scalars(self, bug):
        assert bug.id == 900001
        assert bug.summary == "dev-libs/a: stablereq"
        assert bug.status == "CONFIRMED"
        assert bug.severity == "enhancement"

    def test_sequences_are_tuples(self, bug):
        assert bug.cc == ("amd64@gentoo.org", "x86@gentoo.org", "someone@example.com")
        assert bug.depends_on == (900000,)
        assert bug.blocks == (899999,)
        assert bug.keywords == ("CC-ARCHES",)

    def test_timestamps(self, bug):
        assert bug.last_change_time == datetime.datetime(
            2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC
        )
        assert bug.creation_time == datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)

    def test_null_deadline(self, bug):
        assert bug.deadline is None

    def test_deadline(self):
        bug = parse_bug(RAW_BUG | {"deadline": "2024-03-01"})
        assert bug.deadline == datetime.date(2024, 3, 1)

    def test_package_list(self, bug):
        assert bug.package_list.atoms == (atom("=dev-libs/a-1.2"),)
        assert str(bug.package_list) == "=dev-libs/a-1.2 amd64 x86\r\n"

    def test_flags(self, bug):
        assert bug.flags == (
            Flag(
                name="sanity-check",
                status=FlagStatus.GRANTED,
                id=51984,
                type_id=6,
                setter="nattka@gentoo.org",
            ),
        )

    def test_package_list_knows_its_bug(self, bug):
        # so a malformed list says which bug it came from
        assert bug.package_list.bug_id == 900001

    def test_malformed_package_list_is_attributed(self):
        bug = parse_bug(RAW_BUG | {"cf_stabilisation_atoms": "not an atom"})
        with pytest.raises(PackageListError) as excinfo:
            assert bug.package_list.atoms
        assert excinfo.value.bug_id == 900001
        assert "bug 900001" in str(excinfo.value)

    def test_package_list_without_an_id(self):
        raw = dict(RAW_BUG)
        del raw["id"]
        assert parse_bug(raw).package_list.bug_id is None

    def test_absent_fields_fall_back_to_defaults(self):
        bug = parse_bug({"id": 5})
        assert bug.id == 5
        assert bug.cc == ()
        assert bug.package_list.atoms == ()
        assert bug.runtime_testing_required is RuntimeTesting.UNSET
        assert bug.deadline is None

    def test_empty_response(self):
        assert parse_bug({}) == Bug()

    def test_immutable(self, bug):
        with pytest.raises(dataclasses.FrozenInstanceError):
            bug.summary = "nope"

    def test_hashable(self, bug):
        assert len({bug, parse_bug(RAW_BUG)}) == 1


class TestDerived:
    def test_category(self):
        assert parse_bug(RAW_BUG).category is BugCategory.STABLEREQ
        assert (
            parse_bug(RAW_BUG | {"component": "Keywording"}).category
            is BugCategory.KEYWORDREQ
        )
        assert parse_bug(RAW_BUG | {"component": "Eclasses"}).category is None
        assert parse_bug(RAW_BUG | {"product": "Websites"}).category is None

    def test_resolved(self):
        assert not parse_bug(RAW_BUG).resolved
        assert parse_bug(RAW_BUG | {"resolution": "FIXED"}).resolved
        assert parse_bug(RAW_BUG | {"resolution": "OBSOLETE"}).resolved

    def test_security(self):
        assert not parse_bug(RAW_BUG).security
        assert parse_bug(RAW_BUG | {"product": "Gentoo Security"}).security

    @pytest.mark.parametrize(
        ("status", "expected"),
        (("+", True), ("-", False), ("?", None)),
    )
    def test_sanity_check(self, status, expected):
        flags = [dict(RAW_BUG["flags"][0], status=status)]
        assert parse_bug(RAW_BUG | {"flags": flags}).sanity_check is expected

    def test_sanity_check_unset(self):
        assert parse_bug(RAW_BUG | {"flags": []}).sanity_check is None

    def test_unknown_flag(self):
        assert parse_bug(RAW_BUG).flag("no-such-flag") is None

    def test_url(self):
        assert parse_bug(RAW_BUG).url == "https://bugs.gentoo.org/900001"

    def test_arches(self):
        known = frozenset(("amd64", "x86", "arm"))
        assert parse_bug(RAW_BUG).arches(known) == ("amd64", "x86")

    def test_arches_from_truncated_anonymous_cc(self):
        bug = parse_bug(RAW_BUG | {"cc": ["amd64", "x86", "someone"]})
        assert bug.arches(frozenset(("amd64", "x86"))) == ("amd64", "x86")

    def test_arches_ignores_foreign_domains(self):
        bug = parse_bug(RAW_BUG | {"cc": ["amd64@example.com"]})
        assert bug.arches(frozenset(("amd64",))) == ()

    def test_runtime_testing(self):
        for value, expected in (
            ("Yes", RuntimeTesting.YES),
            ("no", RuntimeTesting.NO),
            ("MANUAL", RuntimeTesting.MANUAL),
            ("---", RuntimeTesting.UNSET),
            ("bogus", RuntimeTesting.UNSET),
        ):
            bug = parse_bug(RAW_BUG | {"cf_runtime_testing_required": value})
            assert bug.runtime_testing_required is expected


class TestParseComment:
    def test_parse(self):
        comment = parse_comment(
            {
                "id": 503,
                "bug_id": 900001,
                "count": 0,
                "text": "please stabilize",
                "creator": "reporter@gentoo.org",
                "time": "2024-01-01T00:00:00Z",
                "creation_time": "2024-01-01T00:00:00Z",
                "is_private": False,
                "tags": ["obsolete"],
            }
        )
        assert comment.id == 503
        assert comment.count == 0
        assert comment.obsolete
        assert comment.creation_time == datetime.datetime(
            2024, 1, 1, tzinfo=datetime.UTC
        )

    def test_not_obsolete(self):
        comment = parse_comment(
            {
                "id": 1,
                "bug_id": 2,
                "count": 1,
                "text": "hi",
                "creator": "x",
                "time": "2024-01-01T00:00:00Z",
                "creation_time": "2024-01-01T00:00:00Z",
                "is_private": False,
                "tags": [],
            }
        )
        assert not comment.obsolete


class TestParseUser:
    def test_parse(self):
        user = parse_user({"id": 7, "name": "dev@gentoo.org", "real_name": "A Dev"})
        assert (user.id, user.name, user.real_name) == (7, "dev@gentoo.org", "A Dev")


class TestParseChanges:
    def test_splits_comma_joined_values(self):
        changes = parse_changes(
            {
                "id": 900001,
                "alias": [],
                "last_change_time": "2024-01-02T03:04:05Z",
                "changes": {
                    "cc": {"added": "amd64@gentoo.org, x86@gentoo.org", "removed": ""},
                    "status": {"added": "RESOLVED", "removed": "CONFIRMED"},
                },
            }
        )
        assert changes.id == 900001
        assert changes.changes["cc"].added == (
            "amd64@gentoo.org",
            "x86@gentoo.org",
        )
        assert changes.changes["cc"].removed == ()
        assert changes.changes["status"].added == ("RESOLVED",)
        assert changes.changes["status"].removed == ("CONFIRMED",)
        assert changes

    def test_empty_changes_is_falsy(self):
        changes = parse_changes(
            {
                "id": 1,
                "alias": [],
                "last_change_time": "2024-01-02T03:04:05Z",
                "changes": {},
            }
        )
        assert not changes
