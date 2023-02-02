import pytest

from pkgcore.scripts import patom
from pkgcore.test.scripts.helpers import ArgParseMixin


class TestFormat(ArgParseMixin):
    _argparser = patom.argparser

    def test_empty(self):
        self.assertOut([], "--format", "%{PACKAGE}")

    def test_unversioned(self):
        self.assertOut(["spork"], "--format", "%{PACKAGE}", "dev-utils/spork")

    def test_versioned(self):
        self.assertOut(["spork"], "--format", "%{PACKAGE}", "dev-utils/spork-1")

    def test_versioned_op(self):
        self.assertOut(["spork"], "--format", "%{PACKAGE}", "=dev-utils/spork-1")

    def test_unversioned_op(self):
        self.assertErr(
            [
                "malformed atom: '=dev-utils/spork': invalid package atom: '=dev-utils/spork'"
            ],
            "--format",
            "%{PACKAGE}",
            "=dev-utils/spork",
        )

    def test_unknown_key(self):
        self.assertErr(
            ["bad format: '%{UNKNOWN}'"], "--format", "%{UNKNOWN}", "dev-utils/spork"
        )

    @pytest.mark.parametrize(
        ("key", "expected"),
        (
            pytest.param("%{CATEGORY}", "dev-utils", id="category"),
            pytest.param("%{PACKAGE}", "spork", id="package"),
            pytest.param("%{VERSION}", "1.2.3_p20221014_p1", id="version"),
            pytest.param("%{FULLVER}", "1.2.3_p20221014_p1-r12", id="fullver"),
            pytest.param("%{REVISION}", "12", id="revision"),
            pytest.param("%{SLOT}", "15", id="slot"),
            pytest.param("%{SUBSLOT}", "2", id="subslot"),
            pytest.param("%{REPO_ID}", "gentoo", id="repo_id"),
            pytest.param("%{OP}", ">=", id="op"),
        ),
    )
    def test_atom_keys(self, key, expected):
        self.assertOut(
            [expected],
            "--format",
            key,
            "!!>=dev-utils/spork-1.2.3_p20221014_p1-r12:15/2::gentoo[use]",
        )

    def test_unset(self):
        self.assertOut(["<unset>"], "--format", "%{VERSION}", "dev-utils/spork")
        self.assertOut([""], "--format", "%[VERSION]", "dev-utils/spork")

    def test_other_text(self):
        self.assertOut(
            ["repo/dev-utils/spork.ebuild"],
            "--format",
            "repo/%{CATEGORY}/%{PACKAGE}.ebuild",
            "dev-utils/spork-2.5",
        )

    @pytest.mark.parametrize(
        "format",
        (
            "%{CATEGORY]",
            "%[CATEGORY}",
            "%{}",
            "%[]",
        ),
    )
    def test_ignore_format(self, format):
        self.assertOut([format], "--format", format, "dev-utils/spork-2.5")
