# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from random import shuffle
from pkgcore.test import TestCase
from pkgcore.ebuild import cpv

class native_CpvTest(TestCase):

    kls = staticmethod(cpv.native_CPV)
    run_cpy_ver_cmp = False

    good_cats = [
        "dev-util", "dev+", "dev-util+", "DEV-UTIL", "aaa0",
        "aaa-0", "multi/depth", "cross-dev_idiot.hacks-suck", "a"]
    bad_cats  = [".util", "_dev", "", "dev-util ", "multi//depth"]
    good_pkgs = ["diffball", "a9", "a9+", "a-100dpi", "a-cvs", "a-3D"]
    bad_pkgs  = ["diffball "]

    good_cp   = [
        "bbb-9/foon", "dev-util/diffball", "dev-util/diffball-a9",
        "dev-ut-asdf/emacs-cvs", "xfce-base/xfce4", "bah/f-100dpi"]

    good_vers = ["1", "2.3.4", "2.3.4a", "02.3", "2.03", "cvs.2", "cvs.2.03"]
    bad_vers  = ["2.3a.4", "2.a.3", "2.3_", "2.3 ", "2.3."]
    simple_good_sufs = ["_alpha", "_beta", "_pre", "_p"]

    suf_nums = list(xrange(100))
    shuffle(suf_nums)

    good_sufs = (simple_good_sufs +["%s%i" % (x, suf_nums.pop())
        for x in simple_good_sufs])
    del suf_nums

    l = len(good_sufs)
    good_sufs = good_sufs + [
        good_sufs[x] + good_sufs[l - x - 1] for x in xrange(l)]
    del l
    bad_sufs  = ["_a", "_9", "_"] + [x+" " for x in simple_good_sufs]
    del simple_good_sufs
    good_revs = ["-r1", "-r300", ""]
    bad_revs = ["-r", "-ra", "-r", "-R1"]

    testing_secondary_args = False

    def make_inst(self, cat, pkg, fullver=""):
        if self.testing_secondary_args:
            return self.kls(cat, pkg, fullver)
        if fullver:
            cpv = "%s/%s-%s" % (cat, pkg, fullver)
        else:
            cpv = "%s/%s" % (cat, pkg)
        return self.kls(cpv)

    def test_simple_key(self):
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
            self.assertRaises(cpv.InvalidCPV, self.make_inst, "da", "ba-3d", "3.3")

    def test_init(self):
        self.kls("dev-util", "diffball", "0.7.1")
        self.kls("dev-util/diffball-0.7.1")
        self.assertRaises(TypeError, self.kls, "dev-util", "diffball")
        self.assertRaises(TypeError, self.kls, "dev-util", "diffball", None)

    def test_parsing(self):
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


    locals()["test_parsing (may take awhile)"] = test_parsing
    del test_parsing

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
            self.assertEqual(c.cpvstr, "%s/%s-%s%s" % (cat, pkg, ver, rev))
            self.assertEqual(c.category, cat)
            self.assertEqual(c.package, pkg)
            self.assertEqual(c.key, "%s/%s" % (cat, pkg))
            if rev == "":
                self.assertEqual(c.revision, None)
            else:
                self.assertEqual(c.revision, int(rev.lstrip("-r")))
            self.assertEqual(c.version, ver)
            self.assertEqual(c.fullver, ver+rev)

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
            c = self.make_inst(cat, pkg, ver + rev)
            self.assertEqual(c.cpvstr, "%s/%s-%s%s" % (cat, pkg, ver, rev))
            self.assertEqual(c.category, cat)
            self.assertEqual(c.package, pkg)
            self.assertEqual(c.key, "%s/%s" % (cat, pkg))
            if rev == "":
                self.assertEqual(c.revision, None)
            else:
                self.assertEqual(c.revision, int(rev.lstrip("-r")))
            self.assertEqual(c.version, ver)
            self.assertEqual(c.fullver, ver + rev)

    def assertGT(self, obj1, obj2):
        self.failUnless(obj1 > obj2, '%r must be > %r' % (obj1, obj2))
        # swap the ordering, so that it's no longer obj1.__cmp__, but obj2s
        self.failUnless(obj2 < obj1, '%r must be < %r' % (obj2, obj1))

        if self.run_cpy_ver_cmp and obj1.fullver and obj2.fullver:
            self.assertTrue(cpv.cpy_ver_cmp(obj1.version, obj1.revision,
                obj2.version, obj2.revision) > 0,
                    'cpy_ver_cmp, %r > %r' % (obj1, obj2))
            self.assertTrue(cpv.cpy_ver_cmp(obj2.version, obj2.revision,
                obj1.version, obj1.revision) < 0,
                    'cpy_ver_cmp, %r < %r' % (obj2, obj1))

    def test_cmp(self):
        kls = self.kls
        self.assertTrue(
            cmp(kls("dev-util/diffball-0.1"),
                kls("dev-util/diffball-0.2")) < 0)
        base = "dev-util/diffball-0.7.1"
        self.assertFalse(cmp(kls(base), kls(base)))
        for rev in ("", "-r1"):
            last = None
            for suf in ["_alpha", "_beta", "_pre", "", "_p"]:
                if suf == "":
                    sufs = [suf]
                else:
                    sufs = [suf, suf+"4"]
                for x in sufs:
                    cur = kls(base+x+rev)
                    self.assertEqual(cur, kls(base+x+rev))
                    if last is not None:
                        self.assertGT(cur, last)

        self.assertGT(
            kls("dev-util/diffball-cvs.6"), kls("dev-util/diffball-600"))
        self.assertGT(
            kls("dev-util/diffball-cvs.7"), kls("dev-util/diffball-cvs.6"))
        self.assertGT(kls("da/ba-6a"), kls("da/ba-6"))
        self.assertGT(kls("da/ba-6a-r1"), kls("da/ba-6a"))
        self.assertGT(kls("da/ba-6.0"), kls("da/ba-6"))
        self.assertGT(kls("da/ba-6.0b"), kls("da/ba-6.0.0"))
        self.assertGT(kls("da/ba-6.02"), kls("da/ba-6.0.0"))
        # float comparison rules.
        self.assertGT(kls("da/ba-6.2"), kls("da/ba-6.054"))
        self.assertEqual(kls("da/ba-6"), kls("da/ba-6"))
        self.assertGT(kls("db/ba"), kls("da/ba"))
        self.assertGT(kls("da/bb"), kls("da/ba"))
        self.assertGT(kls("da/ba-6.0_alpha0_p1"), kls("da/ba-6.0_alpha"))
        self.assertEqual(kls("da/ba-6.0_alpha"), kls("da/ba-6.0_alpha0"))
        self.assertGT(kls("da/ba-6.1"), kls("da/ba-6.09"))
        self.assertGT(kls("da/ba-6.0.1"), kls("da/ba-6.0"))
        for v1, v2 in (("1.001000000000000000001", "1.001000000000000000002"),
            ("1.00100000000", "1.0010000000000000001"),
            ("1.01", "1.1")):
            self.assertGT(kls("da/ba-%s" % v2), kls("da/ba-%s" % v1))
        # Regression test: python does comparison slightly differently
        # if the classes do not match exactly (it prefers rich
        # comparison over __cmp__).
        class DummySubclass(kls):
            pass
        self.assertNotEqual(
            DummySubclass("da/ba-6.0_alpha0_p1"), kls("da/ba-6.0_alpha"))
        self.assertEqual(
            DummySubclass("da/ba-6.0_alpha0"), kls("da/ba-6.0_alpha"))

        self.assertNotEqual(DummySubclass("da/ba-6.0"), "foon")
        self.assertEqual(DummySubclass("da/ba-6.0"), DummySubclass("da/ba-6.0-r0"))

    def test_no_init(self):
        """Test if the cpv is in a somewhat sane state if __init__ fails.

        IPython used to segfault when showing a verbose traceback for
        a subclass of CPV which raised cpv.InvalidCPV. This checks
        if such uninitialized objects survive some basic poking.
        """
        uninited = self.kls.__new__(self.kls)
        broken = self.kls.__new__(self.kls)
        self.assertRaises(cpv.InvalidCPV, broken.__init__, 'broken')
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
        obj = self.kls("dev-util/diffball-1.0-r0")
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
