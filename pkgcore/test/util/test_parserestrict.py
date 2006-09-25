# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild.atom import atom
from pkgcore.restrictions import packages, values, boolean
from pkgcore.util import parserestrict
from pkgcore.util.currying import post_curry


class MatchTest(TestCase):

    def test_comma_separated_containment(self):
        parser = parserestrict.comma_separated_containment('utensil')
        restrict = parser('spork,foon')
        # Icky, should really try to match a fake package.
        self.assertTrue(isinstance(restrict, packages.PackageRestriction))
        self.assertEquals('utensil', restrict.attr)
        valrestrict = restrict.restriction
        self.assertTrue(valrestrict.match(('foon',)))
        self.assertFalse(valrestrict.match(('spork,foon',)))
        self.assertFalse(valrestrict.match(('foo',)))


class TestExtendedRestrictionGeneration(TestCase):

    def verify_text_glob(self, restrict, token):
        self.assertTrue(
            isinstance(restrict, values.StrGlobMatch),
            msg="isinstance testing for %r against %r" % (token, restrict))
        self.assertEqual(
            restrict.prefix, token.endswith("*"),
            msg="testing for %r against %r: val %r" % (
                token, restrict, restrict.prefix))
        self.assertEqual(
            restrict.glob, token.strip("*"),
            msg="verifying the restriciton glob, %r %r" % (
                restrict.glob, token))

    def verify_text(self, restrict, token):
        self.assertTrue(
            isinstance(restrict, values.StrExactMatch),
            msg="verifying restrict %r from %r is StrExactMatch" % (
                restrict, token))
        self.assertEquals(restrict.exact, token)

    def verify_text_containment(self, restrict, token):
        self.assertTrue(
            isinstance(restrict, values.ContainmentMatch),
            msg="verifying restrict %r from %r is ContainmentMatch" % (
                restrict, token))
        self.assertEquals(list(restrict.vals), [token.strip("*")])

    def test_convert_glob(self):
        self.verify_text(parserestrict.convert_glob("diffball"), "diffball")
        for token in ("diff*", "*diff"):
            self.verify_text_glob(parserestrict.convert_glob(token), token)

        for token in ("*", "**", ""):
            i = parserestrict.convert_glob(token)
            self.assertEquals(
                i, None,
                msg="verifying None is returned on pointless restrictions")

        for token in ("*diff*", "*b*"):
            self.verify_text_containment(parserestrict.convert_glob(token),
                                         token)
        self.assertRaises(
            parserestrict.ParseError, parserestrict.convert_glob, '***')

    def verify_restrict(self, restrict, attr, token):
        self.assertTrue(
            isinstance(restrict, packages.PackageRestriction),
            msg="isinstance verification of %r %r" % (token, restrict))
        self.assertEqual(
            restrict.attr, attr,
            msg="verifying package attr %r; required(%s), token %s" % (
                restrict.attr, attr, token))

        if "*" in token:
            self.verify_text_glob(restrict.restriction, token)
        else:
            self.verify_text(restrict.restriction, token)

    def generic_single_restrict_check(self, iscat):
        if iscat:
            sfmts = ["%s/*"]
            attr = "category"
        else:
            sfmts = ["*/%s", "%s"]
            attr = "package"

        for sfmt in sfmts:
            for raw_token in ("package", "*bsdiff", "bsdiff*"):
                token = sfmt % raw_token
                i = parserestrict.parse_match(token)
                self.verify_restrict(i, attr, raw_token)

    test_category = post_curry(generic_single_restrict_check, True)
    test_package = post_curry(generic_single_restrict_check, False)

    def test_combined(self):
        self.assertTrue(
            isinstance(parserestrict.parse_match("dev-util/diffball"), atom))
        for token in ("dev-*/util", "dev-*/util*", "dev-a/util*"):
            i = parserestrict.parse_match(token)
            self.assertTrue(isinstance(i, boolean.AndRestriction))
            self.assertEqual(len(i), 2)
            self.verify_restrict(i[0], "category", token.split("/")[0])
            self.verify_restrict(i[1], "package", token.split("/")[1])

    def test_atom_globbed(self):
        o = parserestrict.parse_match("=sys-devel/gcc-4*")
        self.assertTrue(isinstance(o, atom), msg="%r must be an atom" % o)
