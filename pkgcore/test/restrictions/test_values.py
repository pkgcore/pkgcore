# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


from pkgcore.test import TestRestriction, TestCase
from pkgcore.restrictions import values


class SillyBool(values.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""
    def __init__(self, negate=False):
        object.__setattr__(self, "negate", negate)

    def match(self, something):
        return not self.negate


class BaseTest(TestRestriction):

    def test_force(self):
        self.assertMatches(SillyBool(negate=False), [None], [None]*3)
        self.assertNotMatches(SillyBool(negate=True), [None], [None]*3)


class GetAttrTest(TestRestriction):

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

        args = [pkg, 'value', dummy]
        self.assertForceTrue(succeeds, args)
        self.assertNotForceFalse(succeeds, args)
        self.assertNotForceTrue(fails, args)
        self.assertForceFalse(fails, args)


class StrRegexTest(TestRestriction):

    def test_match(self):
        for negated in (False, True):
            self.assertMatches(values.StrRegex('foo.*r', match=True,
                negate=negated),
                ['foobar'], [None, None, 'foobar'], negated=negated)
            self.assertNotMatches(values.StrRegex('foo.*r', match=True,
                negate=negated),
                ['afoobar'], [None, None, 'afoobar'], negated=negated)

    def test_search(self):
        for negated in (False, True):
            self.assertMatches(values.StrRegex('foo.*r', negate=negated),
                ['asdfoobar'], [None, None, 'asdfoobar'], negated=negated)
            self.assertNotMatches(values.StrRegex('foo.*r', negate=negated),
                ['afobar'], [None, None, 'afobar'], negated=negated)

    def test_case_sensitivity(self):
        self.assertNotMatches(values.StrRegex('foo'), ['FoO'], ['FOo']*3)
        self.assertMatches(values.StrRegex('foo', False), ['FoO'], ['fOo']*3)

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



class native_TestStrExactMatch(TestRestriction):

    if values.base_StrExactMatch is values.native_StrExactMatch:
        kls = values.StrExactMatch
    else:
        class kls(values.native_StrExactMatch, values.base):
            __slots__ = ()
            __inst_caching__ = True
        
            intersect = values._StrExact_intersect
            __repr__ = values._StrExact__repr__
            __str__ = values._StrExact__str__

    kls = staticmethod(kls)

    def test_case_sensitive(self):
        for negated in (False, True):
            self.assertMatches(self.kls('package', negate=negated),
                ['package'], ['package']*3, negated=negated)
            self.assertNotMatches(self.kls('Package', negate=negated),
                ['package'], ['package']*3, negated=negated)

    def test_case_insensitve(self):
        for negated in (False, True):
            self.assertMatches(self.kls('package', case_sensitive=True,
                negate=negated),
                ['package'], ['package']*3, negated=negated)
            self.assertMatches(self.kls('Package', case_sensitive=False,
                 negate=negated),
                ['package'], ['package']*3, negated=negated)

    def test__eq__(self):
        for negate in (True, False):
            self.assertEquals(
                self.kls("rsync", negate=negate),
                self.kls("rsync", negate=negate))
            for x in "Ca":
                self.assertNotEquals(
                    self.kls("rsync", negate=negate),
                    self.kls("rsyn"+x, negate=negate))
            self.assertEquals(
                self.kls(
                    "Rsync", case_sensitive=False, negate=negate),
                self.kls(
                    "rsync", case_sensitive=False, negate=negate))


class cpy_TestStrExactMatch(native_TestStrExactMatch):
    if values.base_StrExactMatch is values.native_StrExactMatch:
        skip = "cpython extension not available"
    else:
        kls = staticmethod(values.StrExactMatch)



class TestStrGlobMatch(TestRestriction):

    def test_matching(self):
        for negated in (True, False):
            self.assertMatches(values.StrGlobMatch('pack', negate=negated),
                ['package'], ['package']*3, negated=negated)
            self.assertNotMatches(values.StrGlobMatch('pack', negate=negated),
                ['apack'], ['apack']*3, negated=negated)
            # case sensitive...
            self.assertMatches(values.StrGlobMatch('pAcK', case_sensitive=False,
                negate=negated),
                ['pack'], ['pack']*3, negated=negated)
            self.assertNotMatches(values.StrGlobMatch('pAcK',
                case_sensitive=True, negate=negated),
                ['pack'], ['pack']*3, negated=negated)
            
            # check prefix.
            self.assertMatches(values.StrGlobMatch('pAck', case_sensitive=False,
                prefix=True, negate=negated),
                ['packa'], ['packa']*3, negated=negated)

            self.assertNotMatches(values.StrGlobMatch('pack', prefix=False,
                negate=negated),
                ['apacka'], ['apacka']*3, negated=negated)

            self.assertMatches(values.StrGlobMatch('pack', prefix=False,
                negate=negated),
                ['apack'], ['apack']*3, negated=negated)

            # daft, but verifies it's not doing contains.
            self.assertNotMatches(values.StrGlobMatch('pack', prefix=False,
                negate=negated),
                ['apacka'], ['apacka']*3, negated=negated)

            self.assertNotMatches(values.StrGlobMatch('pack', prefix=False,
                case_sensitive=False, negate=negated),
                ['aPacka'], ['aPacka']*3, negated=negated)

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


class AnyMatchTest(TestCase):

    # Most of AnyMatch is tested through test_restriction.

    def test_force(self):
        restrict = values.AnyMatch(values.AlwaysTrue)
        self.assertTrue(restrict.force_True(None, None, range(2)))
        self.assertFalse(restrict.force_False(None, None, range(2)))
