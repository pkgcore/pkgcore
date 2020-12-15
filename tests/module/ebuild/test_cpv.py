from random import shuffle

import pytest
from snakeoil.compatibility import cmp

from pkgcore.ebuild import cpv


def generate_misc_sufs():
    simple_good_sufs = ["_alpha", "_beta", "_pre", "_p"]
    suf_nums = list(range(100))
    shuffle(suf_nums)

    good_sufs = (simple_good_sufs + [f"{x}{suf_nums.pop()}" for x in simple_good_sufs])

    l = len(good_sufs)
    good_sufs = good_sufs + [
        good_sufs[x] + good_sufs[l - x - 1] for x in range(l)]

    bad_sufs  = ["_a", "_9", "_"] + [x+" " for x in simple_good_sufs]
    return good_sufs, bad_sufs


class TestCPV:

    good_cats = (
        "dev-util", "dev+", "dev-util+", "DEV-UTIL", "aaa0",
        "aaa-0", "multi/depth", "cross-dev_idiot.hacks-suck", "a")
    bad_cats  = (".util", "_dev", "", "dev-util ", "multi//depth")
    good_pkgs = ("diffball", "a9", "a9+", "a-100dpi", "diff-mode-")
    bad_pkgs  = ("diffball ", "diffball-9", "a-3D", "ab--df", "-df", "+dfa")

    good_cp   = (
        "bbb-9/foon", "dev-util/diffball", "dev-util/diffball-a9",
        "dev-ut-asdf/emacs-cvs", "xfce-base/xfce4", "bah/f-100dpi",
        "dev-util/diffball-blah-monkeys")

    good_vers = ("1", "2.3.4", "2.3.4a", "02.3", "2.03", "3d", "3D")
    bad_vers  = ("2.3a.4", "2.a.3", "2.3_", "2.3 ", "2.3.", "cvs.2")

    good_sufs, bad_sufs = generate_misc_sufs()
    good_revs = ("-r1", "-r300", "-r0", "",
        "-r1000000000000000000")
    bad_revs = ("-r", "-ra", "-r", "-R1")

    testing_secondary_args = False

    def make_inst(self, cat, pkg, fullver=""):
        if self.testing_secondary_args:
            return cpv.CPV(cat, pkg, fullver, versioned=bool(fullver))
        if fullver:
            return cpv.VersionedCPV(f"{cat}/{pkg}-{fullver}")
        return cpv.UnversionedCPV(f"{cat}/{pkg}")

    def test_simple_key(self):
        with pytest.raises(cpv.InvalidCPV):
            self.make_inst("da", "ba-3", "3.3")
        for src in [[("dev-util", "diffball", "0.7.1"), "dev-util/diffball"],
            ["dev-util/diffball"],
            ["dev-perl/mod_perl"],
            ["dev-perl/mod_p"],
            [("dev-perl", "mod-p", ""), "dev-perl/mod-p"],
            ["dev-perl/mod-p-1", "dev-perl/mod-p"],]:
            if len(src) == 1:
                key = src[0]
            else:
                key = src[1]
            if isinstance(src[0], str):
                cat, pkgver = src[0].rsplit("/", 1)
                vals = pkgver.rsplit("-", 1)
                if len(vals) == 1:
                    pkg = pkgver
                    ver = ''
                else:
                    pkg, ver = vals
            else:
                cat, pkg, ver = src[0]

            assert self.make_inst(cat, pkg, ver).key == key

    def test_init(self):
        cpv.CPV("dev-util", "diffball", "0.7.1")
        cpv.CPV("dev-util", "diffball")
        cpv.CPV("dev-util/diffball-0.7.1", versioned=True)
        with pytest.raises(TypeError):
            cpv.VersionedCPV("dev-util", "diffball", None)

    def test_parsing(self):
        # check for gentoo bug 263787
        self.process_pkg(False, 'app-text', 'foo-123-bar')
        self.process_ver(False, 'app-text', 'foo-123-bar', '2.0017a_p', '-r5')
        with pytest.raises(cpv.InvalidCPV):
            cpv.UnversionedCPV('app-text/foo-123')
        for cat_ret, cats in [[False, self.good_cats], [True, self.bad_cats]]:
            for cat in cats:
                for pkg_ret, pkgs in [[False, self.good_pkgs],
                                      [True, self.bad_pkgs]]:
                    for pkg in pkgs:
                        self.process_pkg(cat_ret or pkg_ret, cat, pkg)

        for cp in self.good_cp:
            cat, pkg = cp.rsplit("/", 1)
            for rev_ret, revs in [[False, self.good_revs],
                                  [True, self.bad_revs]]:
                for rev in revs:
                    for ver_ret, vers in [[False, self.good_vers],
                                          [True, self.bad_vers]]:
                        for ver in vers:
                            self.process_ver(ver_ret or rev_ret, cat, pkg,
                                             ver, rev)

        for x in (10, 18, 19, 36, 100):
            assert cpv.CPV("da", "ba", f"1-r0{'0' * x}").revision == 0
            assert \
                int(cpv.CPV("da", "ba", f"1-r1{'0' * x}1").revision) == int(f"1{'0' * x}1")

    def process_pkg(self, ret, cat, pkg):
        if ret:
            with pytest.raises(cpv.InvalidCPV):
                self.make_inst(cat, pkg)
        else:
            c = self.make_inst(cat, pkg)
            assert c.cpvstr == f"{cat}/{pkg}"
            assert c.category == cat
            assert c.package == pkg
            assert c.key == f"{cat}/{pkg}"
            assert c.revision is None
            assert c.version is None
            assert c.fullver is None

    def process_ver(self, ret, cat, pkg, ver, rev):
        if ret:
            with pytest.raises(cpv.InvalidCPV):
                self.make_inst(cat, pkg, f"{ver}{rev}")
        else:
            c = self.make_inst(cat, pkg, ver + rev)
            if rev == "" or rev == "-r0":
                assert c.cpvstr == f"{cat}/{pkg}-{ver}"
                assert c.revision == 0
                if rev:
                    assert c.fullver == ver + rev
                else:
                    assert c.revision == ""
                    assert c.fullver == ver
            else:
                assert c.revision == int(rev.lstrip("-r"))
                assert c.cpvstr == f"{cat}/{pkg}-{ver}{rev}"
                assert c.fullver == ver + rev
            assert c.category == cat
            assert c.package == pkg
            assert c.key == f"{cat}/{pkg}"
            assert c.version == ver

        for suf in self.good_sufs:
            self.process_suf(ret, cat, pkg, ver + suf, rev)
            for bad_suf in self.bad_sufs:
                # double process, front and back.
                self.process_suf(True, cat, pkg, suf + bad_suf, rev)
                self.process_suf(True, cat, pkg, bad_suf + suf, rev)

        for suf in self.bad_sufs:
            # check standalone.
            self.process_suf(True, cat, pkg, ver+suf, rev)

    def process_suf(self, ret, cat, pkg, ver, rev):
        if ret:
            with pytest.raises(cpv.InvalidCPV):
                self.make_inst(cat, pkg, ver+rev)
        else:
            # redundant in light of process_ver... combine these somehow.
            c = self.make_inst(cat, pkg, ver + rev)
            if rev == '' or rev == '-r0':
                assert c.cpvstr == f"{cat}/{pkg}-{ver}"
                assert c.revision == 0
                if rev:
                    assert c.fullver == ver + rev
                else:
                    assert c.revision == ""
                    assert c.fullver == ver
            else:
                assert c.cpvstr == f"{cat}/{pkg}-{ver}{rev}"
                assert c.revision == int(rev.lstrip("-r"))
                assert c.fullver == ver + rev
            assert c.category == cat
            assert c.package == pkg
            assert c.key == f"{cat}/{pkg}"
            assert c.version == ver

    def test_cmp(self):
        ukls, vkls = cpv.UnversionedCPV, cpv.VersionedCPV
        assert vkls("dev-util/diffball-0.1") < vkls("dev-util/diffball-0.2")
        base = "dev-util/diffball-0.7.1"
        assert vkls(base) == vkls(base)
        for rev in ("", "-r1"):
            last = None
            for suf in ["_alpha", "_beta", "_pre", "", "_p"]:
                if suf == "":
                    sufs = [suf]
                else:
                    sufs = [suf, f'{suf}4']
                for x in sufs:
                    cur = vkls(f'{base}{x}{rev}')
                    assert cur == vkls(f'{base}{x}{rev}')
                    if last is not None:
                        assert cur > last

        assert vkls("da/ba-6a") > vkls("da/ba-6")
        assert vkls("da/ba-6a-r1") > vkls("da/ba-6a")
        assert vkls("da/ba-6.0") > vkls("da/ba-6")
        assert vkls("da/ba-6.0.0") > vkls("da/ba-6.0b")
        assert vkls("da/ba-6.02") > vkls("da/ba-6.0.0")
        # float comparison rules.
        assert vkls("da/ba-6.2") > vkls("da/ba-6.054")
        assert vkls("da/ba-6") == vkls("da/ba-6")
        assert ukls("db/ba") > ukls("da/ba")
        assert ukls("da/bb") > ukls("da/ba")
        assert vkls("da/ba-6.0_alpha0_p1") > vkls("da/ba-6.0_alpha")
        assert vkls("da/ba-6.0_alpha") == vkls("da/ba-6.0_alpha0")
        assert vkls("da/ba-6.1") > vkls("da/ba-6.09")
        assert vkls("da/ba-6.0.1") > vkls("da/ba-6.0")
        assert vkls("da/ba-12.2.5") > vkls("da/ba-12.2b")

        # test for gentoo bug 287848
        assert vkls("dev-lang/erlang-12.2.5") > vkls("dev-lang/erlang-12.2b")
        assert vkls("dev-lang/erlang-12.2.5-r1") > vkls("dev-lang/erlang-12.2b")

        # equivalent versions
        assert vkls("da/ba-6.01.0") == vkls("da/ba-6.010.0")
        assert vkls("da/ba-6.0.1") == vkls("da/ba-6.000.1")

        # equivalent revisions
        assert vkls("da/ba-6.01.0") == vkls("da/ba-6.01.0-r0")
        assert vkls("da/ba-6.01.0-r0") == vkls("da/ba-6.01.0-r00")
        assert vkls("da/ba-6.01.0-r1") == vkls("da/ba-6.01.0-r001")

        for v1, v2 in (("1.001000000000000000001", "1.001000000000000000002"),
            ("1.00100000000", "1.0010000000000000001"),
            ("1.01", "1.1")):
            assert vkls(f"da/ba-{v2}") > vkls(f"da/ba-{v1}")

        for x in (18, 36, 100):
            s = "0" * x
            assert vkls(f"da/ba-10{s}1") > vkls(f"da/ba-1{s}1")

        for x in (18, 36, 100):
            s = "0" * x
            assert vkls(f"da/ba-1-r10{s}1") > vkls(f"da/ba-1-r1{s}1")

        assert vkls('sys-apps/net-tools-1.60_p2010081516093') > \
            vkls('sys-apps/net-tools-1.60_p2009072801401')

        assert vkls('sys-apps/net-tools-1.60_p20100815160931') > \
            vkls('sys-apps/net-tools-1.60_p20090728014017')

        assert vkls('sys-apps/net-tools-1.60_p20100815160931') > \
            vkls('sys-apps/net-tools-1.60_p20090728014017-r1')

        # Regression test: python does comparison slightly differently
        # if the classes do not match exactly (it prefers rich
        # comparison over __cmp__).
        class DummySubclass(cpv.CPV):
            pass

        assert DummySubclass("da/ba-6.0_alpha0_p1", versioned=True) != vkls("da/ba-6.0_alpha")
        assert DummySubclass("da/ba-6.0_alpha0", versioned=True) == vkls("da/ba-6.0_alpha")

        assert DummySubclass("da/ba-6.0", versioned=True) != "foon"
        assert DummySubclass("da/ba-6.0", versioned=True) == \
            DummySubclass("da/ba-6.0-r0", versioned=True)

    def test_no_init(self):
        """Test if the cpv is in a somewhat sane state if __init__ fails.

        IPython used to segfault when showing a verbose traceback for
        a subclass of CPV which raised cpv.InvalidCPV. This checks
        if such uninitialized objects survive some basic poking.
        """
        uninited = cpv.CPV.__new__(cpv.CPV)
        broken = cpv.CPV.__new__(cpv.CPV)
        with pytest.raises(cpv.InvalidCPV):
            broken.__init__('broken', versioned=True)
        for thing in (uninited, broken):
            # the c version returns None, the py version does not have the attr
            getattr(thing, 'cpvstr', None)
            repr(thing)
            str(thing)
            # The c version returns a constant, the py version raises
            try:
                hash(thing)
            except AttributeError:
                pass

    def test_r0_revisions(self):
        # single '0'
        obj = cpv.CPV("dev-util/diffball-1.0-r0", versioned=True)
        assert obj.cpvstr == "dev-util/diffball-1.0"
        assert str(obj) == "dev-util/diffball-1.0"
        assert obj.fullver == "1.0-r0"
        assert obj.revision == 0

        # multiple '0'
        obj = cpv.CPV("dev-util/diffball-1.0-r000", versioned=True)
        assert obj.cpvstr == "dev-util/diffball-1.0"
        assert str(obj) == "dev-util/diffball-1.0"
        assert obj.fullver == "1.0-r000"
        assert obj.revision == 0

        # single '0' prefix
        obj = cpv.CPV("dev-util/diffball-1.0-r01", versioned=True)
        assert obj.cpvstr == "dev-util/diffball-1.0-r1"
        assert str(obj) == "dev-util/diffball-1.0-r1"
        assert obj.fullver == "1.0-r01"
        assert obj.revision == 1

        # multiple '0' prefixes
        obj = cpv.CPV("dev-util/diffball-1.0-r0001", versioned=True)
        assert obj.cpvstr == "dev-util/diffball-1.0-r1"
        assert str(obj) == "dev-util/diffball-1.0-r1"
        assert obj.fullver == "1.0-r0001"
        assert obj.revision == 1

    def test_attribute_errors(self):
        obj = cpv.VersionedCPV("foo/bar-0")
        assert not obj == 0
        assert obj != 0
        with pytest.raises(TypeError):
            assert obj < 0
        with pytest.raises(TypeError):
            assert obj <= 0
        with pytest.raises(TypeError):
            assert obj > 0
        with pytest.raises(TypeError):
            assert obj >= 0
