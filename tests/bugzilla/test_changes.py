import datetime

import pytest

from pkgcore.bugzilla.changes import (
    MAX_COMMENT_LENGTH,
    BugUpdate,
    FlagChange,
    ListChange,
    NewBug,
    NewComment,
    summarise,
)
from pkgcore.bugzilla.enums import (
    BugCategory,
    Component,
    FlagStatus,
    Product,
    Resolution,
    RuntimeTesting,
    Severity,
    Status,
)
from pkgcore.bugzilla.errors import BugzillaUsageError
from pkgcore.bugzilla.pkglist import PackageList


class TestListChange:
    def test_empty_is_falsy(self):
        assert not ListChange()
        assert ListChange().to_wire() == {}

    def test_adding(self):
        assert ListChange.adding("a", "b").to_wire() == {"add": ["a", "b"]}

    def test_removing(self):
        assert ListChange.removing("a").to_wire() == {"remove": ["a"]}

    def test_setting(self):
        assert ListChange.setting("a", "b").to_wire() == {"set": ["a", "b"]}

    def test_setting_empty_still_serialises(self):
        # an explicit "clear the field", distinct from leaving it alone
        assert ListChange.setting().to_wire() == {"set": []}
        assert ListChange.setting()

    def test_add_and_remove(self):
        assert ListChange(add=("a",), remove=("b",)).to_wire() == {
            "add": ["a"],
            "remove": ["b"],
        }

    def test_ints_are_stringified(self):
        assert ListChange.adding(1, 2).to_wire() == {"add": ["1", "2"]}

    def test_replace_conflicts_with_add(self):
        with pytest.raises(BugzillaUsageError, match="replace cannot be combined"):
            ListChange(add=("a",), replace=("b",))

    def test_overlapping_add_and_remove(self):
        with pytest.raises(BugzillaUsageError, match="both added and removed"):
            ListChange(add=("a",), remove=("a",))

    def test_merge(self):
        merged = ListChange.adding("a") | ListChange(add=("b",), remove=("c",))
        assert merged.to_wire() == {"add": ["a", "b"], "remove": ["c"]}

    def test_merge_deduplicates(self):
        assert (ListChange.adding("a") | ListChange.adding("a")).add == ("a",)

    def test_merge_with_replace_wins(self):
        merged = ListChange.adding("a") | ListChange.setting("z")
        assert merged.to_wire() == {"set": ["z"]}

    def test_frozen(self):
        change = ListChange.adding("a")
        with pytest.raises(AttributeError):
            change.add = ()


class TestNewComment:
    def test_to_wire(self):
        assert NewComment("hello").to_wire() == {"body": "hello"}

    def test_private(self):
        assert NewComment("hi", is_private=True).to_wire() == {
            "body": "hi",
            "is_private": True,
        }

    def test_rejects_overlong_body(self):
        with pytest.raises(BugzillaUsageError, match="the limit is"):
            NewComment("x" * (MAX_COMMENT_LENGTH + 1))

    def test_truncated_leaves_short_bodies_alone(self):
        assert NewComment.truncated("short").body == "short"

    def test_truncated_cuts_on_a_line_boundary(self):
        body = "\n".join(f"line {i}" for i in range(100))
        comment = NewComment.truncated(body, limit=50)
        assert len(comment.body) <= 50
        assert comment.body.endswith("\n...\n")
        assert "line 0" in comment.body

    def test_truncated_without_newlines(self):
        comment = NewComment.truncated("x" * 100, limit=20)
        assert len(comment.body) <= 20
        assert comment.body.endswith("\n...\n")


class TestSummarise:
    def test_single_package_keeps_the_version(self):
        pkglist = PackageList("=dev-libs/a-1 amd64")
        assert summarise(pkglist, BugCategory.STABLEREQ) == "dev-libs/a-1: stablereq"

    def test_keywordreq_suffix(self):
        pkglist = PackageList("dev-libs/a ~amd64")
        assert summarise(pkglist, BugCategory.KEYWORDREQ) == "dev-libs/a: keywordreq"

    def test_several_packages(self):
        pkglist = PackageList("=dev-libs/a-1\n=dev-libs/b-2")
        assert summarise(pkglist, BugCategory.STABLEREQ) == (
            "dev-libs/a-1, dev-libs/b-2: stablereq"
        )

    def test_long_list_collapses(self):
        pkglist = PackageList(
            "\n".join(f"=dev-libs/averylongpackagename{i}-1" for i in range(10))
        )
        assert summarise(pkglist, BugCategory.STABLEREQ) == (
            "dev-libs/averylongpackagename0-1 and friends: stablereq"
        )

    def test_single_long_package_is_not_collapsed(self):
        pkglist = PackageList(f"=dev-libs/{'a' * 120}-1")
        assert summarise(pkglist, BugCategory.STABLEREQ).startswith("dev-libs/aaa")

    def test_empty_list(self):
        with pytest.raises(BugzillaUsageError, match="empty package list"):
            summarise(PackageList(), BugCategory.STABLEREQ)


class TestNewBug:
    def test_minimal(self):
        bug = NewBug(
            summary="a summary",
            description="a description",
            component=Component.CURRENT_PACKAGES,
        )
        assert bug.to_wire() == {
            "product": "Gentoo Linux",
            "component": "Current packages",
            "summary": "a summary",
            "description": "a description",
            "version": "unspecified",
            "severity": "normal",
        }

    def test_rejects_blank_summary(self):
        with pytest.raises(BugzillaUsageError, match="needs a summary"):
            NewBug(summary="  ", description="x", component=Component.ECLASSES)

    def test_full(self):
        bug = NewBug(
            summary="s",
            description="d",
            component=Component.VULNERABILITIES,
            product=Product.GENTOO_SECURITY,
            severity=Severity.QA,
            assigned_to="a@gentoo.org",
            cc=("b@gentoo.org",),
            keywords=("SECURITY",),
            depends_on=(1,),
            blocks=(2,),
            see_also=("https://bugs.gentoo.org/3",),
            deadline=datetime.date(2024, 3, 1),
            package_list=PackageList("=dev-libs/a-1"),
            runtime_testing_required=RuntimeTesting.MANUAL,
        )
        assert bug.to_wire() == {
            "product": "Gentoo Security",
            "component": "Vulnerabilities",
            "summary": "s",
            "description": "d",
            "version": "unspecified",
            "severity": "QA",
            "assigned_to": "a@gentoo.org",
            "cc": ["b@gentoo.org"],
            "keywords": ["SECURITY"],
            "depends_on": [1],
            "blocks": [2],
            "see_also": ["https://bugs.gentoo.org/3"],
            "deadline": "2024-03-01",
            "cf_stabilisation_atoms": "=dev-libs/a-1",
            "cf_runtime_testing_required": "Manual",
        }

    def test_no_ids_key(self):
        # ids belongs to updates; sending it on create would be silently ignored
        with pytest.raises(TypeError):
            NewBug(summary="s", description="d", component="x", ids=[1])


class TestArchRequest:
    @pytest.fixture
    def pkglist(self):
        return PackageList("=dev-libs/a-1 amd64\n=dev-libs/b-2 x86")

    def test_stablereq(self, pkglist):
        wire = NewBug.arch_request(
            BugCategory.STABLEREQ, pkglist, maintainers=("m@gentoo.org", "o@gentoo.org")
        ).to_wire()
        assert wire["product"] == "Gentoo Linux"
        assert wire["component"] == "Stabilization"
        assert wire["severity"] == "enhancement"
        assert wire["summary"] == "dev-libs/a-1, dev-libs/b-2: stablereq"
        assert wire["assigned_to"] == "m@gentoo.org"
        assert wire["cc"] == ["o@gentoo.org"]
        assert "keywords" not in wire
        assert wire["cf_stabilisation_atoms"] == str(pkglist)

    def test_keywordreq(self, pkglist):
        wire = NewBug.arch_request(BugCategory.KEYWORDREQ, pkglist).to_wire()
        assert wire["component"] == "Keywording"
        assert wire["description"] == "Please keyword the listed packages."

    def test_unmaintained_falls_back(self, pkglist):
        wire = NewBug.arch_request(BugCategory.STABLEREQ, pkglist).to_wire()
        assert wire["assigned_to"] == "maintainer-needed@gentoo.org"
        assert "cc" not in wire

    def test_cc_arches(self, pkglist):
        wire = NewBug.arch_request(
            BugCategory.STABLEREQ, pkglist, cc_arches=True
        ).to_wire()
        assert wire["keywords"] == ["CC-ARCHES"]

    def test_explicit_summary_and_description(self, pkglist):
        wire = NewBug.arch_request(
            BugCategory.STABLEREQ, pkglist, summary="custom", description="why"
        ).to_wire()
        assert wire["summary"] == "custom"
        assert wire["description"] == "why"

    def test_extra_kwargs_pass_through(self, pkglist):
        wire = NewBug.arch_request(
            BugCategory.STABLEREQ, pkglist, depends_on=(7,)
        ).to_wire()
        assert wire["depends_on"] == [7]


class TestPackageMask:
    def test_deadline_and_cc(self):
        wire = NewBug.package_mask(
            "dev-libs/a: removal",
            "unmaintained",
            rites=30,
            maintainers=("m@gentoo.org", "o@gentoo.org"),
            today=datetime.date(2024, 1, 1),
        ).to_wire()
        assert wire["component"] == "Current packages"
        assert wire["keywords"] == ["PMASKED"]
        assert wire["assigned_to"] == "m@gentoo.org"
        assert wire["cc"] == ["o@gentoo.org", "treecleaner@gentoo.org"]
        assert wire["deadline"] == "2024-01-31"

    def test_unmaintained(self):
        wire = NewBug.package_mask(
            "s", "d", rites=30, today=datetime.date(2024, 1, 1)
        ).to_wire()
        assert wire["assigned_to"] == "maintainer-needed@gentoo.org"
        assert wire["cc"] == ["treecleaner@gentoo.org"]


class TestBugUpdate:
    def test_empty_is_falsy(self):
        assert not BugUpdate()

    def test_empty_still_carries_ids(self):
        assert BugUpdate().to_wire([1]) == {"ids": [1]}

    def test_needs_ids(self):
        with pytest.raises(BugzillaUsageError, match="at least one bug id"):
            BugUpdate(summary="x").to_wire([])

    def test_full_id_list_is_always_sent(self):
        # bugzilla lets the body override the path id, so it must be complete
        assert BugUpdate(summary="x").to_wire([1, 2, 3])["ids"] == [1, 2, 3]

    def test_cc_add_is_rejected(self):
        with pytest.raises(TypeError):
            BugUpdate(cc_add=["amd64@gentoo.org"])

    def test_list_fields(self):
        wire = BugUpdate(
            cc=ListChange.adding("amd64@gentoo.org"),
            keywords=ListChange(add=("ALLARCHES",), remove=("CC-ARCHES",)),
            blocks=ListChange.adding(5),
            depends_on=ListChange.removing(6),
            see_also=ListChange.adding("https://bugs.gentoo.org/7"),
            groups=ListChange.setting("gentoo-security"),
        ).to_wire([1])
        assert wire["cc"] == {"add": ["amd64@gentoo.org"]}
        assert wire["keywords"] == {"add": ["ALLARCHES"], "remove": ["CC-ARCHES"]}
        assert wire["blocks"] == {"add": ["5"]}
        assert wire["depends_on"] == {"remove": ["6"]}
        assert wire["see_also"] == {"add": ["https://bugs.gentoo.org/7"]}
        assert wire["groups"] == {"set": ["gentoo-security"]}

    def test_empty_list_fields_are_omitted(self):
        assert BugUpdate(summary="x").to_wire([1]).keys() == {"ids", "summary"}

    def test_scalars(self):
        wire = BugUpdate(
            summary="new summary",
            assigned_to="m@gentoo.org",
            whiteboard="B3 [ebuild]",
            deadline=datetime.date(2024, 3, 1),
            package_list=PackageList("=dev-libs/a-1 amd64"),
            runtime_testing_required=RuntimeTesting.YES,
        ).to_wire([1])
        assert wire["summary"] == "new summary"
        assert wire["assigned_to"] == "m@gentoo.org"
        assert wire["whiteboard"] == "B3 [ebuild]"
        assert wire["deadline"] == "2024-03-01"
        assert wire["cf_stabilisation_atoms"] == "=dev-libs/a-1 amd64"
        assert wire["cf_runtime_testing_required"] == "Yes"

    def test_flags(self):
        wire = BugUpdate(
            flags=(FlagChange("sanity-check", FlagStatus.DENIED),)
        ).to_wire([1])
        assert wire["flags"] == [{"name": "sanity-check", "status": "-"}]

    def test_flag_requestee(self):
        change = FlagChange("review", FlagStatus.REQUESTED, requestee="a@gentoo.org")
        assert change.to_wire() == {
            "name": "review",
            "status": "?",
            "requestee": "a@gentoo.org",
        }


class TestBugUpdateValidation:
    def test_resolution_needs_status(self):
        with pytest.raises(BugzillaUsageError, match="needs an explicit status"):
            BugUpdate(resolution=Resolution.FIXED)

    def test_resolved_needs_resolution(self):
        with pytest.raises(BugzillaUsageError, match="needs a resolution"):
            BugUpdate(status=Status.RESOLVED)

    def test_duplicate_needs_dupe_of(self):
        with pytest.raises(BugzillaUsageError, match="dupe_of"):
            BugUpdate(status=Status.RESOLVED, resolution=Resolution.DUPLICATE)

    def test_dupe_of_needs_duplicate(self):
        with pytest.raises(BugzillaUsageError, match="dupe_of"):
            BugUpdate(status=Status.RESOLVED, resolution=Resolution.FIXED, dupe_of=5)

    def test_duplicate_pair(self):
        wire = BugUpdate(
            status=Status.RESOLVED, resolution=Resolution.DUPLICATE, dupe_of=5
        ).to_wire([1])
        assert wire["resolution"] == "DUPLICATE"
        assert wire["dupe_of"] == 5

    def test_status_alone_is_fine(self):
        assert BugUpdate(status=Status.IN_PROGRESS).to_wire([1])["status"] == (
            "IN_PROGRESS"
        )


class TestShorthands:
    @pytest.mark.parametrize(
        ("status", "expected"), ((True, "+"), (False, "-"), (None, "X"))
    )
    def test_sanity_check(self, status, expected):
        wire = BugUpdate.sanity_check(status).to_wire([1])
        assert wire["flags"] == [{"name": "sanity-check", "status": expected}]
        assert "comment" not in wire

    def test_sanity_check_with_comment(self):
        wire = BugUpdate.sanity_check(False, comment="broken").to_wire([1])
        assert wire["comment"] == {"body": "broken"}

    def test_sanity_check_with_extra_fields(self):
        wire = BugUpdate.sanity_check(
            True, cc=ListChange.adding("amd64@gentoo.org")
        ).to_wire([1])
        assert wire["cc"] == {"add": ["amd64@gentoo.org"]}

    def test_resolve(self):
        wire = BugUpdate.resolve(comment="all arches done").to_wire([1])
        assert wire["status"] == "RESOLVED"
        assert wire["resolution"] == "FIXED"
        assert wire["comment"] == {"body": "all arches done"}

    def test_resolve_with_uncc(self):
        wire = BugUpdate.resolve(
            comment="done", cc=ListChange.removing("amd64@gentoo.org")
        ).to_wire([1])
        assert wire["cc"] == {"remove": ["amd64@gentoo.org"]}

    def test_obsoleted_by(self):
        wire = BugUpdate.obsoleted_by(999).to_wire([1, 2])
        assert wire == {
            "ids": [1, 2],
            "status": "RESOLVED",
            "resolution": "OBSOLETE",
            "see_also": {"add": ["https://bugs.gentoo.org/999"]},
        }
