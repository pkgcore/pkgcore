import textwrap
from unittest import mock

import pytest

from pkgcore.ebuild import domain as domain_mod
from pkgcore.ebuild import profiles
from pkgcore.fs.livefs import iter_scan
from pkgcore.restrictions import packages

from .test_profiles import profile_mixin


class TestDomain:
    @pytest.fixture(autouse=True, scope="function")
    def _setup(self, tmp_path_factory):
        self.confdir = tmp_path_factory.mktemp("conf")
        self.rootdir = tmp_path_factory.mktemp("root")
        self.pmixin = profile_mixin()
        self.profile_base = tmp_path_factory.mktemp("profiles")
        self.profile1 = self.profile_base / "profile1"
        self.pmixin.mk_profile(self.profile_base, str(self.profile1))
        self.pusedir = self.confdir / "package.use"
        self.pusedir.mkdir()

    def mk_domain(self):
        return domain_mod.domain(
            profiles.OnDiskProfile(str(self.profile_base), "profile1"),
            [],
            [],
            ROOT=self.rootdir,
            config_dir=self.confdir,
        )

    def test_sorting(self):
        """assert that configuration files are read in alphanum ordering"""
        # assert the base state; no files, no content.
        assert () == self.mk_domain().pkg_use

        open(self.pusedir / "00", "w").write("*/* X")
        open(self.pusedir / "01", "w").write("*/* -X Y")

        # Force the returned ordering to be reversed; this is to assert that
        # the domain forces a sort.
        orig_func = iter_scan

        def rev_iter_scan(*args, **kwargs):
            return iter(sorted(orig_func(*args, **kwargs), reverse=True))

        with mock.patch(
            "pkgcore.fs.livefs.iter_scan", side_effect=rev_iter_scan
        ), mock.patch("pkgcore.ebuild.domain.iter_scan", side_effect=rev_iter_scan):
            assert (
                (packages.AlwaysTrue, ((), ("X",))),
                (packages.AlwaysTrue, (("X",), ("Y",))),
            ) == self.mk_domain().pkg_use

    def test_use_expand_syntax(self):
        open(self.pusedir / "a", "w").write(
            textwrap.dedent(
                """
                */* x_y1
                # unrelated is there to verify that it's unaffected by the USE_EXPAND
                */* unrelated X: -y1 y2
                """
            )
        )

        assert (
            (packages.AlwaysTrue, ((), ("x_y1",))),
            (
                packages.AlwaysTrue,
                (
                    ("x_y1",),
                    (
                        "unrelated",
                        "x_y2",
                    ),
                ),
            ),
        ) == self.mk_domain().pkg_use

    def test_use_flag_parsing_enforcement(self):
        open(self.pusedir / "a", "w").write("*/* X:")
        # TODO: need to catch the warning here, but I'm not sure how.
        # Meanwhile, ensure that the failed token is ignored.
        assert ((packages.AlwaysTrue, ((), ())),) == self.mk_domain().pkg_use
