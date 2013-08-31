# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.test import TestCase
from snakeoil.osutils import pjoin
from snakeoil.currying import post_curry

from pkgcore.ebuild import cpv
from pkgcore.pkgsets import glsa
from snakeoil.test.mixins import TempDirMixin
from pkgcore.restrictions.packages import OrRestriction


# misc setup code for generating glsas for testing

glsa_template = \
"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE glsa SYSTEM "http://www.gentoo.org/dtd/glsa.dtd">
<?xml-stylesheet href="/xsl/glsa.xsl" type="text/xsl"?>
<?xml-stylesheet href="/xsl/guide.xsl" type="text/xsl"?>

<glsa id="%s">
  <title>generated glsa for %s</title>
  <synopsis>
    foon
  </synopsis>
  <product type="ebuild">foon</product>
  <announced>2003-11-23</announced>
  <revised>2003-11-23: 01</revised>
  <bug>33989</bug>
  <access>remote</access>
  <affected>%s</affected>
  <background>
    <p>FreeRADIUS is a popular open source RADIUS server.</p>
  </background>
  <description>
    <p>foon</p>
  </description>
  <impact type="normal">
    <p>
    impact-rific
    </p>
  </impact>
  <workaround>
    <p>redundant if no workaround</p>
  </workaround>
  <resolution>
    <p>blarh</p>
  </resolution>
  <references>
    <uri link="http://www.securitytracker.com/alerts/2003/Nov/1008263.html">SecurityTracker.com Security Alert</uri>
  </references>
</glsa>
"""

ops = {'>':'gt', '<':'lt'}
ops.update((k+'=', v[0] + 'e') for k, v in ops.items())
ops.update(('~' + k, 'r' + v) for k, v in ops.items())
ops['='] = 'eq'
def convert_range(text, tag):
    i = 0
    while text[i] in "><=~":
        i += 1
    op = text[:i]
    text = text[i:]
    range = ops[op]
    return '<%s range="%s">%s</%s>' % (tag, range, text, tag)


def mk_glsa(*pkgs, **kwds):
    id = kwds.pop("id", None)
    if kwds:
        raise TypeError("id is the only allowed kwds; got %r" % kwds)
    id = str(id)
    horked = ''
    for data in pkgs:
        if len(data) == 3:
            pkg, ranges, arch = data
        else:
            pkg, ranges = data
            arch = '*'
        horked += '<package name="%s" auto="yes" arch="%s">%s%s\n</package>' \
            % (pkg, arch,
            '\n'.join(convert_range(x, 'unaffected') for x in ranges[0]),
            '\n'.join(convert_range(x, 'vulnerable') for x in ranges[1]))
    return glsa_template % (id, id, horked)


# yay.  now we can actually do tests :P

pkgs_set = (
    (("dev-util/diffball", ([], ["~>=0.7-r1"]))
    ),
    (("dev-util/bsdiff", ([">=2"], [">1"]))
    ))

class TestGlsaDirSet(TempDirMixin, TestCase):

    def mk_glsa(self, feed):
        for idx, data in enumerate(feed):
            open(pjoin(self.dir, "glsa-200611-%02i.xml" % idx),
                "w").write(mk_glsa(data))

    def check_range(self, vuln_range, ver_matches, ver_nonmatches):
        self.mk_glsa([("dev-util/diffball", ([], [vuln_range]))])
        restrict = list(OrRestriction(*tuple(glsa.GlsaDirSet(self.dir))))
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
