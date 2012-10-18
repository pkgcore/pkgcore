# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from random import shuffle
from pkgcore.test import TestCase
from snakeoil.test import mk_cpy_loadable_testcase
from pkgcore.ebuild import cpv
from snakeoil.compatibility import cmp

def generate_misc_sufs():
    simple_good_sufs = ["_alpha", "_beta", "_pre", "_p"]
    suf_nums = list(xrange(100))
    shuffle(suf_nums)

    good_sufs = (simple_good_sufs +["%s%i" % (x, suf_nums.pop())
        for x in simple_good_sufs])

    l = len(good_sufs)
    good_sufs = good_sufs + [
        good_sufs[x] + good_sufs[l - x - 1] for x in xrange(l)]

    bad_sufs  = ["_a", "_9", "_"] + [x+" " for x in simple_good_sufs]
    return good_sufs, bad_sufs


class native_CpvTest(TestCase):

    kls = staticmethod(cpv.native_CPV)

    @classmethod
    def vkls(cls, *args):
        return cls.kls(versioned=True, *args)

    def ukls(cls, *args):
        return cls.kls(versioned=False, *args)

    run_cpy_ver_cmp = False

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
            return self.kls(cat, pkg, fullver, versioned=bool(fullver))
        if fullver:
            return self.vkls("%s/%s-%s" % (cat, pkg, fullver))
        return self.ukls("%s/%s" % (cat, pkg))

    def test_simple_key(self):
        self.assertRaises(cpv.InvalidCPV, self.make_inst, "da", "ba-3", "3.3")
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
            if isinstance(src[0], basestring):
                cat, pkgver = src[0].rsplit("/", 1)
                vals = pkgver.rsplit("-", 1)
                if len(vals) == 1:
                    pkg = pkgver
                    ver = ''
                else:
                    pkg, ver = vals
            else:
                cat, pkg, ver = src[0]

            self.assertEqual(self.make_inst(cat, pkg, ver).key, key)

    def test_init(self):
        self.kls("dev-util", "diffball", "0.7.1")
        self.kls("dev-util/diffball-0.7.1", versioned=True)
        self.assertRaises(TypeError, self.kls, "dev-util", "diffball")
        self.assertRaises(TypeError, self.vkls, "dev-util", "diffball", None)

    def test_parsing(self):
        # check for gentoo bug 263787
        self.process_pkg(False, 'app-text', 'foo-123-bar')
        self.process_ver(False, 'app-text', 'foo-123-bar', '2.0017a_p', '-r5')
        self.assertRaises(cpv.InvalidCPV, self.ukls, 'app-text/foo-123')
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
            self.assertEqual(self.kls("da", "ba", "1-r0%s" % ("0" * x)).revision,
                None)
            self.assertEqual(long(self.kls("da", "ba", "1-r1%s1" % ("0" * x)).revision),
                long("1%s1" % ("0" * x)))


    def process_pkg(self, ret, cat, pkg):
        if ret:
            self.assertRaisesMsg("%s/%s" % (cat,pkg), cpv.InvalidCPV,
                self.make_inst, cat, pkg)
        else:
            c = self.make_inst(cat, pkg)
            self.assertEqual(c.cpvstr, "%s/%s" % (cat, pkg))
            self.assertEqual(c.category, cat)
            self.assertEqual(c.package, pkg)
            self.assertEqual(c.key, "%s/%s" % (cat, pkg))
            self.assertEqual(c.revision, None)
            self.assertEqual(c.version, None)
            self.assertEqual(c.fullver, None)

    def process_ver(self, ret, cat, pkg, ver, rev):
        if ret:
            self.assertRaisesMsg("%s/%s-%s%s" % (cat, pkg, ver, rev),
                cpv.InvalidCPV, self.make_inst,
                cat, pkg,  "%s%s" % (ver, rev))
        else:
            c = self.make_inst(cat, pkg, ver + rev)
            if rev == "" or rev == "-r0":
                self.assertEqual(c.cpvstr, "%s/%s-%s" % (cat, pkg, ver))
                self.assertEqual(c.revision, None)
                self.assertEqual(c.fullver, ver)
            else:
                self.assertEqual(c.revision, int(rev.lstrip("-r")))
                self.assertEqual(c.cpvstr, "%s/%s-%s%s" % (cat, pkg, ver, rev))
                self.assertEqual(c.fullver, ver+rev)
            self.assertEqual(c.category, cat)
            self.assertEqual(c.package, pkg)
            self.assertEqual(c.key, "%s/%s" % (cat, pkg))
            self.assertEqual(c.version, ver)

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
            self.assertRaisesMsg("%s/%s-%s%s" % (cat, pkg, ver, rev),
                cpv.InvalidCPV, self.make_inst,
                cat, pkg, ver+rev)
        else:
            # redundant in light of process_ver... combine these somehow.
            c = self.make_inst(cat, pkg, ver + rev)
            if rev == '' or rev == '-r0':
                self.assertEqual(c.cpvstr, "%s/%s-%s" % (cat, pkg, ver))
                self.assertEqual(c.revision, None)
                self.assertEqual(c.fullver, ver)
            else:
                self.assertEqual(c.cpvstr, "%s/%s-%s%s" % (cat, pkg, ver, rev))
                self.assertEqual(c.revision, int(rev.lstrip("-r")))
                self.assertEqual(c.fullver, ver + rev)
            self.assertEqual(c.category, cat)
            self.assertEqual(c.package, pkg)
            self.assertEqual(c.key, "%s/%s" % (cat, pkg))
            self.assertEqual(c.version, ver)

    def assertGT(self, obj1, obj2):
        self.assertTrue(obj1 > obj2, '%r must be > %r' % (obj1, obj2))
        # swap the ordering, so that it's no longer obj1.__cmp__, but obj2s
        self.assertTrue(obj2 < obj1, '%r must be < %r' % (obj2, obj1))

        if self.run_cpy_ver_cmp and obj1.fullver and obj2.fullver:
            self.assertTrue(cpv.cpy_ver_cmp(obj1.version, obj1.revision,
                obj2.version, obj2.revision) > 0,
                    'cpy_ver_cmp, %r > %r' % (obj1, obj2))
            self.assertTrue(cpv.cpy_ver_cmp(obj2.version, obj2.revision,
                obj1.version, obj1.revision) < 0,
                    'cpy_ver_cmp, %r < %r' % (obj2, obj1))

    def test_cmp(self):
        ukls, vkls = self.ukls, self.vkls
        self.assertTrue(
            cmp(vkls("dev-util/diffball-0.1"),
                vkls("dev-util/diffball-0.2")) < 0)
        base = "dev-util/diffball-0.7.1"
        self.assertFalse(cmp(vkls(base), vkls(base)))
        for rev in ("", "-r1"):
            last = None
            for suf in ["_alpha", "_beta", "_pre", "", "_p"]:
                if suf == "":
                    sufs = [suf]
                else:
                    sufs = [suf, suf+"4"]
                for x in sufs:
                    cur = vkls(base+x+rev)
                    self.assertEqual(cur, vkls(base+x+rev))
                    if last is not None:
                        self.assertGT(cur, last)

        self.assertGT(vkls("da/ba-6a"), vkls("da/ba-6"))
        self.assertGT(vkls("da/ba-6a-r1"), vkls("da/ba-6a"))
        self.assertGT(vkls("da/ba-6.0"), vkls("da/ba-6"))
        self.assertGT(vkls("da/ba-6.0.0"), vkls("da/ba-6.0b"))
        self.assertGT(vkls("da/ba-6.02"), vkls("da/ba-6.0.0"))
        # float comparison rules.
        self.assertGT(vkls("da/ba-6.2"), vkls("da/ba-6.054"))
        self.assertEqual(vkls("da/ba-6"), vkls("da/ba-6"))
        self.assertGT(ukls("db/ba"), ukls("da/ba"))
        self.assertGT(ukls("da/bb"), ukls("da/ba"))
        self.assertGT(vkls("da/ba-6.0_alpha0_p1"), vkls("da/ba-6.0_alpha"))
        self.assertEqual(vkls("da/ba-6.0_alpha"), vkls("da/ba-6.0_alpha0"))
        self.assertGT(vkls("da/ba-6.1"), vkls("da/ba-6.09"))
        self.assertGT(vkls("da/ba-6.0.1"), vkls("da/ba-6.0"))
        self.assertGT(vkls("da/ba-12.2.5"), vkls("da/ba-12.2b"))

        # test for gentoo bug 287848
        self.assertGT(vkls("dev-lang/erlang-12.2.5"),
            vkls("dev-lang/erlang-12.2b"))
        self.assertGT(vkls("dev-lang/erlang-12.2.5-r1"),
            vkls("dev-lang/erlang-12.2b"))

        self.assertEqual(vkls("da/ba-6.01.0"), vkls("da/ba-6.010.0"))

        for v1, v2 in (("1.001000000000000000001", "1.001000000000000000002"),
            ("1.00100000000", "1.0010000000000000001"),
            ("1.01", "1.1")):
            self.assertGT(vkls("da/ba-%s" % v2), vkls("da/ba-%s" % v1))

        for x in (18, 36, 100):
            s = "0" * x
            self.assertGT(vkls("da/ba-10%s1" % s), vkls("da/ba-1%s1" % s))

        for x in (18, 36, 100):
            s = "0" * x
            self.assertGT(vkls("da/ba-1-r10%s1" % s),
                vkls("da/ba-1-r1%s1" % s))

        self.assertGT(vkls('sys-apps/net-tools-1.60_p2010081516093'),
            vkls('sys-apps/net-tools-1.60_p2009072801401'))

        self.assertGT(vkls('sys-apps/net-tools-1.60_p20100815160931'),
            vkls('sys-apps/net-tools-1.60_p20090728014017'))

        self.assertGT(vkls('sys-apps/net-tools-1.60_p20100815160931'),
            vkls('sys-apps/net-tools-1.60_p20090728014017-r1'))

        # Regression test: python does comparison slightly differently
        # if the classes do not match exactly (it prefers rich
        # comparison over __cmp__).
        class DummySubclass(self.kls):
            pass
        self.assertNotEqual(
            DummySubclass("da/ba-6.0_alpha0_p1", versioned=True),
                vkls("da/ba-6.0_alpha"))
        self.assertEqual(
            DummySubclass("da/ba-6.0_alpha0", versioned=True),
                vkls("da/ba-6.0_alpha"))

        self.assertNotEqual(DummySubclass("da/ba-6.0", versioned=True),
            "foon")
        self.assertEqual(DummySubclass("da/ba-6.0", versioned=True),
            DummySubclass("da/ba-6.0-r0", versioned=True))

    def test_no_init(self):
        """Test if the cpv is in a somewhat sane state if __init__ fails.

        IPython used to segfault when showing a verbose traceback for
        a subclass of CPV which raised cpv.InvalidCPV. This checks
        if such uninitialized objects survive some basic poking.
        """
        uninited = self.kls.__new__(self.kls)
        broken = self.kls.__new__(self.kls)
        self.assertRaises(cpv.InvalidCPV, broken.__init__, 'broken', versioned=True)
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

    def test_r0_removal(self):
        obj = self.kls("dev-util/diffball-1.0-r0", versioned=True)
        self.assertEqual(obj.fullver, "1.0")
        self.assertEqual(obj.revision, None)
        self.assertEqual(str(obj), "dev-util/diffball-1.0")


class CPY_CpvTest(native_CpvTest):
    if cpv.cpy_builtin:
        kls = staticmethod(cpv.cpy_CPV)
    else:
        skip = "cpython cpv extension not available"

    run_cpy_ver_cmp = True


class CPY_Cpv_OptionalArgsTest(CPY_CpvTest):

    testing_secondary_args = True

test_cpy_used = mk_cpy_loadable_testcase('pkgcore.ebuild._cpv',
    "pkgcore.ebuild.cpv", "CPV_base", "CPV")

