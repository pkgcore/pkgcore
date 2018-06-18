# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from snakeoil.currying import post_curry
from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin

from pkgcore.ebuild import cpv
from pkgcore.pkgsets import glsa
from pkgcore.restrictions.packages import OrRestriction
from pkgcore.restrictions.restriction import AlwaysBool
from pkgcore.test.misc import mk_glsa

pkgs_set = (
    (("dev-util/diffball", ([], ["~>=0.7-r1"]))
    ),
    (("dev-util/bsdiff", ([">=2"], [">1"]))
    ))


class TestGlsaDirSet(TempDirMixin, TestCase):

    def mk_glsa(self, feed):
        for idx, data in enumerate(feed):
            with open(pjoin(self.dir, "glsa-200611-%02i.xml" % idx), "w") as f:
                f.write(mk_glsa(data))

    def check_range(self, vuln_range, ver_matches, ver_nonmatches):
        self.mk_glsa([("dev-util/diffball", ([], [vuln_range]))])
        restrict = list(OrRestriction(*tuple(glsa.GlsaDirSet(self.dir))))
        if len(restrict) == 0: # exception thrown
            restrict.append(AlwaysBool(negate=False))
        self.assertEqual(len(restrict), 1)
        restrict = restrict[0]
        for ver in ver_matches:
            pkg = cpv.versioned_CPV("dev-util/diffball-%s" % ver)
            self.assertTrue(restrict.match(pkg),
                msg="pkg %s must match for %r: %s" %
                    (pkg, vuln_range, restrict))

        for ver in ver_nonmatches:
            pkg = cpv.versioned_CPV("dev-util/diffball-%s" % ver)
            self.assertFalse(restrict.match(pkg),
                msg="pkg %s must not match for %r: %s" %
                    (pkg, vuln_range, restrict))

    test_range_ge = post_curry(check_range, ">=1-r2",
        ["1-r2", "1-r7", "2"], ["0", "1"])
    test_range_gt = post_curry(check_range, ">1-r2",
        ["1-r7", "2"], ["0", "1", "1-r2"])
    test_range_le = post_curry(check_range, "<=1-r2",
        ["1", "1-r1"], ["1-r3", "2"])
    test_range_lt = post_curry(check_range, "<1-r2",
        ["1", "1-r0"], ["1-r2", "2"])
    test_range_eq = post_curry(check_range, "=1-r2",
        ["1-r2"], ["1-r3", "1", "2"])
    test_range_eq_glob = post_curry(check_range, "=1*",
        ["1-r2", "1.0.2", "10"], ["2", "3", "0"])
    test_range_rge = post_curry(check_range, "~>=1-r2",
        ["1-r2", "1-r7"], ["2", "1-r1", "1"])
    test_range_rgt = post_curry(check_range, "~>1-r1",
        ["1-r2", "1-r6"], ["2", "1-r1", "1"])
    test_range_rle = post_curry(check_range, "~<=1-r2",
        ["1-r2", "1", "1-r1"], ["2", "0.9", "1-r3"])
    test_range_rlt = post_curry(check_range, "~<1-r2",
        ["1", "1-r1"], ["2", "0.9", "1-r2"])
    test_range_rge_r0 = post_curry(check_range, "~>=2",
        ["2", "2-r1"], ["1", "2_p1", "2.1", "3"])
    test_range_rgt_r0 = post_curry(check_range, "~>2",
        ["2-r1", "2-r2"], ["1", "2", "2_p1", "2.1"])
    test_range_rle_r0 = post_curry(check_range, "~<=2",
        ["2"], ["1", "2-r1", "2_p1", "3"])
    test_range_rlt_r0 = post_curry(check_range, "~<2",
        [], ["1", "2", "2-r1", "2.1", "3"])

    def test_iter(self):
        self.mk_glsa(pkgs_set)
        g = glsa.GlsaDirSet(self.dir)
        l = list(g)
        self.assertEqual(set(x.key for x in l),
            set(['dev-util/diffball', 'dev-util/bsdiff']))

    def test_pkg_grouped_iter(self):
        self.mk_glsa(pkgs_set + (("dev-util/bsdiff", ([], ["~>=2-r1"])),))
        g = glsa.GlsaDirSet(self.dir)
        l = list(g.pkg_grouped_iter(sorter=sorted))
        self.assertEqual(set(x.key for x in l),
            set(['dev-util/diffball', 'dev-util/bsdiff']))
        # main interest is dev-util/bsdiff
        r = l[0]
        pkgs = [cpv.versioned_CPV("dev-util/bsdiff-%s" % ver) for ver in
            ("0", "1", "1.1", "2", "2-r1")]
        self.assertEqual([x.fullver for x in pkgs if r.match(x)],
            ["1.1", "2-r1"])
