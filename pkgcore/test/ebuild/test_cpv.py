# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest
from pkgcore.ebuild import cpv


class native_CpvTest(unittest.TestCase):

    kls = staticmethod(cpv.native_CPV)
    good_cats = [
        "dev-util", "asdf", "dev+", "dev-util+", "DEV-UTIL", "aaa0", "zzz9",
        "aaa-0", "bbb-9"]
    bad_cats  = ["dev.util", "dev_", "", "dev-util "]
    good_pkgs = ["diffball", "a9", "a9+", "a-100dpi", "a-cvs"]
    bad_pkgs  = ["diffball "]

    good_cp   = [
        "bbb-9/foon", "dev-util/diffball", "dev-util/diffball-a9",
        "dev-ut-asdf/emacs-cvs", "xfce-base/xfce4", "bah/f-100dpi"]

    good_vers = ["1", "2.3.4", "2.3.4a", "02.3", "2.03"]
    good_vers = ["cvs.%s" % x for x in good_vers] + good_vers
    bad_vers  = ["2.3a.4", "2.a.3", "2.3_", "2.3 ", "2.3."]
    simple_good_sufs = ["_alpha", "_beta", "_pre", "_p"]
    good_sufs = (simple_good_sufs +
                 ["%s1" % x for x in simple_good_sufs] +
                 ["%s932" % x for x in simple_good_sufs])
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
            self.assertRaises(cpv.InvalidCPV, self.make_inst, cat, pkg)
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
            self.assertRaises(
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
            self.assertRaises(
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


    def verify_gt(self, obj1, obj2):
        self.assertTrue(cmp(obj1, obj2) > 0)
        self.assertTrue(cmp(obj2, obj1) < 0)

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
                    self.assertEqual(cmp(cur, kls(base+x+rev)), 0)
                    if last is not None:
                        self.verify_gt(cur, last)

        self.verify_gt(
            kls("dev-util/diffball-cvs.6"), kls("dev-util/diffball-600"))
        self.verify_gt(
            kls("dev-util/diffball-cvs.7"), kls("dev-util/diffball-cvs.6"))
        self.verify_gt(kls("da/ba-6a"), kls("da/ba-6"))
        self.verify_gt(kls("da/ba-6a-r1"), kls("da/ba-6a"))

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


class CPY_CpvTest(native_CpvTest):
    if cpv.cpy_builtin:
        kls = staticmethod(cpv.cpy_CPV)
    else:
        skip = "cpython cpv extension not available"

class CPY_Cpv_OptionalArgsTest(CPY_CpvTest):

    testing_secondary_args = True
