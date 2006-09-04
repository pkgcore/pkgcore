# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.package.atom import atom
from pkgcore.restrictions import packages, values, boolean
from pkgcore.util.commandline import generate_restriction, convert_glob
from pkgcore.util.currying import post_curry

class TestExtendedRestrictionGeneration(unittest.TestCase):

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
        self.verify_text(convert_glob("diffball"), "diffball")
        for token in ("diff*", "*diff"):
            self.verify_text_glob(convert_glob(token), token)

        for token in ("*", "**", ""):
            i = convert_glob(token)
            self.assertEquals(
                i, None,
                msg="verifying None is returned on pointless restrictions")

        for token in ("*diff*", "*b*"):
            self.verify_text_containment(convert_glob(token), token)

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
                i = generate_restriction(token)
                self.verify_restrict(i, attr, raw_token)

    test_category = post_curry(generic_single_restrict_check, True)
    test_package = post_curry(generic_single_restrict_check, False)

    def test_combined(self):
        self.assertTrue(
            isinstance(generate_restriction("dev-util/diffball"), atom))
        for token in ("dev-*/util", "dev-*/util*", "dev-a/util*"):
            i = generate_restriction(token)
            self.assertTrue(isinstance(i, boolean.AndRestriction))
            self.assertEqual(len(i), 2)
            self.verify_restrict(i[0], "category", token.split("/")[0])
            self.verify_restrict(i[1], "package", token.split("/")[1])
