# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild.atom import atom
from pkgcore.restrictions import packages, values, boolean
from pkgcore.util import parserestrict
from pkgcore.util.currying import post_curry
from pkgcore.repository import util


class MatchTest(TestCase):

    def test_comma_separated_containment(self):
        parser = parserestrict.comma_separated_containment('utensil')
        restrict = parser('spork,foon')
        # Icky, should really try to match a fake package.
        self.assertInstance(restrict, packages.PackageRestriction)
        self.assertEqual('utensil', restrict.attr)
        valrestrict = restrict.restriction
        self.assertTrue(valrestrict.match(('foon',)))
        self.assertFalse(valrestrict.match(('spork,foon',)))
        self.assertFalse(valrestrict.match(('foo',)))


class TestExtendedRestrictionGeneration(TestCase):

    def assertInstance(self, restrict, kls, token):
        TestCase.assertInstance(self, restrict, kls,
            msg="got %r, expected %r for %r" % (restrict, kls, token))

    def verify_text_glob(self, restrict, token):
        self.assertInstance(restrict, values.StrGlobMatch, token)
        self.assertEqual(
            restrict.prefix, token.endswith("*"),
            msg="testing for %r against %r: val %r" % (
                token, restrict, restrict.prefix))
        self.assertEqual(
            restrict.glob, token.strip("*"),
            msg="verifying the restriciton glob, %r %r" % (
                restrict.glob, token))

    def verify_text(self, restrict, token):
        self.assertInstance(restrict, values.StrExactMatch, token)
        self.assertEqual(restrict.exact, token)

    def verify_text_containment(self, restrict, token):
        self.assertInstance(restrict, values.ContainmentMatch, token)
        self.assertEqual(list(restrict.vals), [token.strip("*")])

    def test_convert_glob(self):
        self.verify_text(parserestrict.convert_glob("diffball"), "diffball")
        for token in ("diff*", "*diff"):
            self.verify_text_glob(parserestrict.convert_glob(token), token)

        for token in ("*", "**", ""):
            i = parserestrict.convert_glob(token)
            self.assertEqual(
                i, None,
                msg="verifying None is returned on pointless restrictions")

        for token in ("*diff*", "*b*"):
            self.verify_text_containment(parserestrict.convert_glob(token),
                                         token)
        self.assertRaises(
            parserestrict.ParseError, parserestrict.convert_glob, '***')

    def verify_restrict(self, restrict, attr, token):
        self.assertInstance(restrict, packages.PackageRestriction, token)
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
        self.assertInstance(parserestrict.parse_match("dev-util/diffball"),
            atom, "dev-util/diffball")
        for token in ("dev-*/util", "dev-*/util*", "dev-a/util*"):
            i = parserestrict.parse_match(token)
            self.assertInstance(i, boolean.AndRestriction, token)
            self.assertEqual(len(i), 2)
            self.verify_restrict(i[0], "category", token.split("/")[0])
            self.verify_restrict(i[1], "package", token.split("/")[1])

    def test_atom_globbed(self):
        self.assertInstance(parserestrict.parse_match("=sys-devel/gcc-4*"),
            atom, "=sys-devel/gcc-4*")

    def test_use_atom(self):
        o = parserestrict.parse_match("net-misc/openssh[-X]")
        self.assertInstance(o, atom, "net-misc/openssh[-X]")
        self.assertTrue(o.use)

    def test_slot_atom(self):
        o = parserestrict.parse_match("sys-devel/automake:1.6")
        self.assertInstance(o, atom, "sys-devel/automake:1.6")
        self.assertTrue(o.slot)


class ParsePVTest(TestCase):

    def setUp(self):
        self.repo = util.SimpleTree({
                'spork': {
                    'foon': ('1', '2'),
                    'spork': ('1', '2'),
                    },
                'foon': {
                    'foon': ('2', '3'),
                    }})


    def test_parse_pv(self):
        for input, output in [
            ('spork/foon-3', 'spork/foon-3'),
            ('spork-1', 'spork/spork-1'),
            ('foon-3', 'foon/foon-3'),
            ]:
            self.assertEqual(
                output,
                parserestrict.parse_pv(self.repo, input).cpvstr)
        for bogus in [
            'spork',
            'foon-2',
            ]:
            self.assertRaises(
                parserestrict.ParseError,
                parserestrict.parse_pv, self.repo, bogus)
