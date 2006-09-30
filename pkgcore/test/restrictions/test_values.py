# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


from pkgcore.test import TestCase
from pkgcore.restrictions import values


class SillyBool(values.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""
    def match(self, something):
        return not self.negate


class BaseTest(TestCase):

    def test_force(self):
        true = SillyBool(negate=False)
        false = SillyBool(negate=True)
        self.failUnless(true.force_True(None, None, None))
        self.failIf(true.force_False(None, None, None))
        self.failIf(false.force_True(None, None, None))
        self.failUnless(false.force_False(None, None, None))


class GetAttrTest(TestCase):

    """Test bits of GetAttrRestriction that differ from PackageRestriction."""

    def test_force(self):
        # TODO we could do with both more tests and a more powerful
        # force_* implementation. This just tests if the function
        # takes the right number of arguments.

        # TODO test negate handling
        succeeds = values.GetAttrRestriction('test', values.AlwaysTrue)
        fails = values.GetAttrRestriction('test', values.AlwaysFalse)

        class Dummy(object):
            test = True

        dummy = Dummy()

        class FakePackage(object):
            """XXX this is vastly too minimal."""
            value = dummy

        pkg = FakePackage()

        self.failUnless(succeeds.force_True(pkg, 'value', dummy))
        self.failIf(succeeds.force_False(pkg, 'value', dummy))
        self.failIf(fails.force_True(pkg, 'value', dummy))
        self.failUnless(fails.force_False(pkg, 'value', dummy))


class StrRegexTest(TestCase):

    def test_match(self):
        for x in (True, False):
            self.assertEquals(x, values.StrRegex(
                    'foo.*r', match=True, negate=not x).match('foobar'))
            self.assertEquals(not x, values.StrRegex(
                    'foo.*r', match=True, negate=not x).match('afoobar'))

    def test_search(self):
        for x in (True, False):
            self.assertEquals(x, values.StrRegex(
                    'foo.*r', negate=not x).match('afoobar'))
            self.assertEquals(not x, values.StrRegex(
                    '^foo.*r', negate=not x).match('afoobar'))

    def test_case_sensitivity(self):
        self.assertEquals(False, values.StrRegex('foo').match('FOO'))
        self.assertEquals(True, values.StrRegex('foo', False).match('FOO'))

    def test_str(self):
        self.assertEquals('search spork', str(values.StrRegex('spork')))
        self.assertEquals('not search spork',
                          str(values.StrRegex('spork', negate=True)))
        self.assertEquals('match spork',
                          str(values.StrRegex('spork', match=True)))
        self.assertEquals('not match spork',
                          str(values.StrRegex('spork',
                                              match=True, negate=True)))

    def test_repr(self):
        for restr, string in [
            (values.StrRegex('spork'), "<StrRegex 'spork' search @"),
            (values.StrRegex('spork', match=True),
             "<StrRegex 'spork' match @"),
            (values.StrRegex('spork', negate=True),
             "<StrRegex 'spork' negated search @"),
            ]:
            self.failUnless(repr(restr).startswith(string), (restr, string))


class TestStrExactMatch(TestCase):

    def test_case_sensitive(self):
        for x in (True, False):
            self.assertEquals(
                values.StrExactMatch("package", negate=not x).match("package"),
                x)
            self.assertEquals(
                values.StrExactMatch("portage", negate=not x).match("portage"),
                x)
            self.assertEquals(
                values.StrExactMatch("Package", negate=not x).match("package"),
                not x)
            self.assertEquals(
                values.StrExactMatch("diffball", negate=not x).match("bsdiff"),
                not x)

    def test_case_insensitve(self):
        for x in (True, False):
            self.assertEquals(
                values.StrExactMatch(
                    "Rsync", case_sensitive=False, negate=not x).match(
                    "rsync"),
                x)
            self.assertEquals(
                values.StrExactMatch(
                    "rsync", case_sensitive=False, negate=not x).match(
                    "RSYnC"),
                x)
            self.assertEquals(
                values.StrExactMatch(
                    "PackageA", case_sensitive=False, negate=not x).match(
                    "package"),
                not x)
            self.assertEquals(
                values.StrExactMatch(
                    "diffball", case_sensitive=False, negate=not x).match(
                    "bsdiff"), not x)

    def test__eq__(self):
        for negate in (True, False):
            self.assertEquals(
                values.StrExactMatch("rsync", negate=negate),
                values.StrExactMatch("rsync", negate=negate))
            for x in "Ca":
                self.assertNotEquals(
                    values.StrExactMatch("rsync", negate=negate),
                    values.StrExactMatch("rsyn"+x, negate=negate))
            self.assertEquals(
                values.StrExactMatch(
                    "Rsync", case_sensitive=False, negate=negate),
                values.StrExactMatch(
                    "rsync", case_sensitive=False, negate=negate))


class TestStrGlobMatch(TestCase):

    def test_case_sensitive(self):
        for x in (True, False):
            self.assertEquals(
                values.StrGlobMatch("pack", negate=not x).match("package"), x)
            self.assertEquals(
                values.StrGlobMatch("package", negate=not x).match("package"),
                x)
            self.assertEquals(
                values.StrGlobMatch("port", negate=not x).match("portage"), x)
            self.assertEquals(
                values.StrGlobMatch("portagea", negate=not x).match("portage"),
                not x)
            self.assertEquals(
                values.StrGlobMatch("Package", negate=not x).match("package"),
                not x)
            self.assertEquals(
                values.StrGlobMatch("diffball", negate=not x).match("bsdiff"),
                not x)

    def test_case_insensitve(self):
        for x in (True, False):
            for y in ("c", ''):
                self.assertEquals(
                    values.StrGlobMatch(
                        "Rsyn"+y, case_sensitive=False, negate=not x).match(
                        "rsync"), x)
                self.assertEquals(
                    values.StrGlobMatch(
                        "rsyn"+y, case_sensitive=False, negate=not x).match(
                        "RSYnC"), x)
            self.assertEquals(
                values.StrGlobMatch(
                    "PackageA", case_sensitive=False, negate=not x).match(
                    "package"), not x)
            self.assertEquals(
                values.StrGlobMatch(
                    "diffball", case_sensitive=False, negate=not x).match(
                    "bsdiff"), not x)

    def test__eq__(self):
        self.assertFalse(
            values.StrGlobMatch("rsync", prefix=False) ==
            values.StrGlobMatch("rsync", prefix=True))
        for negate in (True, False):
            self.assertEquals(
                values.StrGlobMatch("rsync", negate=negate),
                values.StrGlobMatch("rsync", negate=negate))
            for x in "Ca":
                self.assertNotEquals(
                    values.StrGlobMatch("rsync", negate=negate),
                    values.StrGlobMatch("rsyn"+x, negate=negate))
            self.assertEquals(
                values.StrGlobMatch(
                    "Rsync", case_sensitive=False, negate=negate),
                values.StrGlobMatch(
                    "rsync", case_sensitive=False, negate=negate))
        self.assertNotEqual(
            values.StrGlobMatch("rsync", negate=True),
            values.StrGlobMatch("rsync", negate=False))


class TestEqualityMatch(TestCase):

    def test_match(self):
        for x, y, ret in (("asdf", "asdf", True), ("asdf", "fdsa", False),
            (1, 1, True), (1,2, False),
            (list(range(2)), list(range(2)), True),
            (range(2), reversed(range(2)), False),
            (True, True, True),
            (True, False, False),
            (False, True, False)):
            for negate in (True, False):
                self.assertEquals(
                    values.EqualityMatch(x, negate=negate).match(y),
                    ret != negate,
                    msg="testing %s==%s, required %s, negate=%s" % (
                        repr(x),repr(y), ret, negate))

    def test__eq__(self):
        for negate in (True, False):
            self.assertEqual(
                values.EqualityMatch("asdf", negate=negate),
                values.EqualityMatch("asdf", negate=negate))
            self.assertNotEqual(
                values.EqualityMatch(1, negate=negate),
                values.EqualityMatch(2, negate=negate))
        self.assertNotEqual(
            values.EqualityMatch("asdf", negate=True),
            values.EqualityMatch("asdf", negate=False))


class TestContainmentMatch(TestCase):

    def test_match(self):
        for x, y, ret in (
            (range(10), range(10), True),
            (range(10), [], False),
            (range(10), set(xrange(10)), True),
            (set(xrange(10)), range(10), True)):
            for negate in (True, False):
                self.assertEquals(
                    values.ContainmentMatch(
                        negate=negate, disable_inst_caching=True, *x).match(y),
                    ret != negate)
        for negate in (True, False):
            self.assertEquals(
                values.ContainmentMatch(
                    all=True, negate=negate, *range(10)).match(range(10)),
                not negate)
        self.assertEquals(values.ContainmentMatch("asdf").match("fdsa"), False)
        self.assertEquals(values.ContainmentMatch("asdf").match("asdf"), True)
        self.assertEquals(
            values.ContainmentMatch("asdf").match("aasdfa"), True)
        self.assertEquals(
            values.ContainmentMatch("asdf", "bzip").match("pbzip2"), True)

    def test_force_basestring(self):
        restrict = values.ContainmentMatch('asdf', 'bzip')
        self.assertEquals(True, restrict.force_True(None, None, 'pbzip2'))
        self.assertEquals(False, restrict.force_False(None, None, 'pbzip2'))

    def test__eq__(self):
        for negate in (True, False):
            self.assertEquals(
                values.ContainmentMatch(negate=negate, *range(100)),
                values.ContainmentMatch(negate=negate, *range(100)),
                msg="range(100), negate=%s" % negate)
            self.assertNotEqual(values.ContainmentMatch(1, negate=not negate),
                values.ContainmentMatch(1, negate=negate))
            self.assertEqual(
                values.ContainmentMatch(1, 2, 3, all=True, negate=negate),
                values.ContainmentMatch(1, 2, 3, all=True, negate=negate))
            self.assertNotEqual(
                values.ContainmentMatch(1, 2, all=True, negate=negate),
                values.ContainmentMatch(1, 2, 3, all=True, negate=negate))
            self.assertNotEqual(
                values.ContainmentMatch(1, 2, 3, all=False, negate=negate),
                values.ContainmentMatch(1, 2, 3, all=True, negate=negate))


class FlatteningRestrictionTest(TestCase):

    def test_basic(self):
        for negate in (False, True):
            inst = values.FlatteningRestriction(
                tuple, values.AnyMatch(values.EqualityMatch(None)),
                negate=negate)
            self.assertEqual(not negate, inst.match([7, 8, [9, None]]))
            self.assertEqual(negate, inst.match([7, 8, (9, None)]))
            # Just check this does not raise
            self.assertTrue(str(inst))
            self.assertTrue(repr(inst))


class FunctionRestrictionTest(TestCase):

    def test_basic(self):

        def yes(val):
            return True
        def no(val):
            return False

        for negate in (False, True):
            yes_restrict = values.FunctionRestriction(yes, negate=negate)
            no_restrict = values.FunctionRestriction(no, negate=negate)
            self.assertEqual(not negate, yes_restrict.match(7))
            self.assertEqual(negate, no_restrict.match(7))
            for restrict in yes_restrict, no_restrict:
                # Just check this does not raise
                self.assertTrue(str(restrict))
                self.assertTrue(repr(restrict))
