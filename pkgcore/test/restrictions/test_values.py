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

    kls = values.StrRegex
    
    def test_match(self):
        for negated in (False, True):
            self.assertMatches(self.kls('foo.*r', match=True,
                negate=negated),
                ['foobar'], [None, None, 'foobar'], negated=negated)
            self.assertNotMatches(self.kls('foo.*r', match=True,
                negate=negated),
                ['afoobar'], [None, None, 'afoobar'], negated=negated)

    def test_search(self):
        for negated in (False, True):
            self.assertMatches(self.kls('foo.*r', negate=negated),
                ['asdfoobar'], [None, None, 'asdfoobar'], negated=negated)
            self.assertNotMatches(self.kls('foo.*r', negate=negated),
                ['afobar'], [None, None, 'afobar'], negated=negated)

    def test_case_sensitivity(self):
        self.assertNotMatches(self.kls('foo'), ['FoO'], ['FOo']*3)
        self.assertMatches(self.kls('foo', False), ['FoO'], ['fOo']*3)

    def test_str(self):
        self.assertEquals('search spork', str(self.kls('spork')))
        self.assertEquals('not search spork',
                          str(self.kls('spork', negate=True)))
        self.assertEquals('match spork',
                          str(self.kls('spork', match=True)))
        self.assertEquals('not match spork',
                          str(self.kls('spork',
                                              match=True, negate=True)))

    def test_repr(self):
        for restr, string in [
            (self.kls('spork'), "<StrRegex 'spork' search @"),
            (self.kls('spork', match=True),
             "<StrRegex 'spork' match @"),
            (self.kls('spork', negate=True),
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

    def test_case_insensitive(self):
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

    kls = values.StrGlobMatch

    def test_matching(self):
        for negated in (True, False):
            self.assertMatches(self.kls('pack', negate=negated),
                ['package'], ['package']*3, negated=negated)
            self.assertNotMatches(self.kls('pack', negate=negated),
                ['apack'], ['apack']*3, negated=negated)
            # case sensitive...
            self.assertMatches(self.kls('pAcK', case_sensitive=False,
                negate=negated),
                ['pack'], ['pack']*3, negated=negated)
            self.assertNotMatches(self.kls('pAcK',
                case_sensitive=True, negate=negated),
                ['pack'], ['pack']*3, negated=negated)
            
            # check prefix.
            self.assertMatches(self.kls('pAck', case_sensitive=False,
                prefix=True, negate=negated),
                ['packa'], ['packa']*3, negated=negated)

            self.assertNotMatches(self.kls('pack', prefix=False,
                negate=negated),
                ['apacka'], ['apacka']*3, negated=negated)

            self.assertMatches(self.kls('pack', prefix=False,
                negate=negated),
                ['apack'], ['apack']*3, negated=negated)

            # daft, but verifies it's not doing contains.
            self.assertNotMatches(self.kls('pack', prefix=False,
                negate=negated),
                ['apacka'], ['apacka']*3, negated=negated)

            self.assertNotMatches(self.kls('pack', prefix=False,
                case_sensitive=False, negate=negated),
                ['aPacka'], ['aPacka']*3, negated=negated)

    def test__eq__(self):
        self.assertFalse(
            self.kls("rsync", prefix=False) ==
            self.kls("rsync", prefix=True))
        for negate in (True, False):
            self.assertEquals(
                self.kls("rsync", negate=negate),
                self.kls("rsync", negate=negate))
            for x in "Ca":
                self.assertNotEquals(
                    self.kls("rsync", negate=negate),
                    self.kls("rsyn"+x, negate=negate))
            self.assertNotEquals(
                self.kls("Rsync", case_sensitive=False, negate=negate),
                self.kls("rsync", case_sensitive=True, negate=negate))
            self.assertNotEquals(
                self.kls("rsync", case_sensitive=False, negate=negate),
                self.kls("rsync", case_sensitive=True, negate=negate))
            self.assertNotEquals(
                self.kls("rsync", case_sensitive=False, negate=negate),
                self.kls("rsync", case_sensitive=True, negate=not negate))
        self.assertNotEqual(
            self.kls("rsync", negate=True),
            self.kls("rsync", negate=False))


class TestEqualityMatch(TestRestriction):

    kls = staticmethod(values.EqualityMatch)

    def test_match(self):
        for x, y, ret in (("asdf", "asdf", True), ("asdf", "fdsa", False),
            (1, 1, True), (1,2, False),
            (list(range(2)), list(range(2)), True),
            (range(2), reversed(range(2)), False),
            (True, True, True),
            (True, False, False),
            (False, True, False)):
            for negated in (True, False):
                self.assertMatches(self.kls(x, negate=negated),
                    [y], [y]*3, negated=(ret ^ (not negated)))

    def test__eq__(self):
        for negate in (True, False):
            self.assertEqual(
                self.kls("asdf", negate=negate),
                self.kls("asdf", negate=negate))
            self.assertNotEqual(
                self.kls(1, negate=negate),
                self.kls(2, negate=negate))
        self.assertNotEqual(
            self.kls("asdf", negate=True),
            self.kls("asdf", negate=False))


class TestContainmentMatch(TestRestriction):

    kls = values.ContainmentMatch

    def test_match(self):
        for x, y, ret in (
            (range(10), range(10), True),
            (range(10), [], False),
            (range(10), set(xrange(10)), True),
            (set(xrange(10)), range(10), True)):

            for negated in (False, True):
                self.assertMatches(self.kls(negate=negated,
                    disable_inst_caching=True, *x),
                    [y], [y]*3, negated=(ret == negated))

        for negated in (False, True):
            # intentionally differing for the force_* args; slips in
            # an extra data set for testing.
            self.assertMatches(self.kls(all=True, negate=negated, *range(10)),
                [range(20)], [range(10)]*3, negated=negated)
            self.assertNotMatches(self.kls(all=True, negate=negated,
                *range(10)),
                [range(5)], [range(5)]*3, negated=negated)

        self.assertNotMatches(self.kls("asdf"), ["fdsa"], ["fdas"]*3)
        self.assertMatches(self.kls("asdf"), ["asdf"], ["asdf"]*3)
        self.assertMatches(self.kls("asdf"), ["asdffdsa"], ["asdffdsa"]*3)
        self.assertMatches(self.kls("b"), ["aba"], ["aba"]*3)

    def test__eq__(self):
        for negate in (True, False):
            self.assertEquals(
                self.kls(negate=negate, *range(100)),
                self.kls(negate=negate, *range(100)),
                msg="range(100), negate=%s" % negate)
            self.assertNotEqual(self.kls(1, negate=not negate),
                self.kls(1, negate=negate))
            self.assertEqual(
                self.kls(1, 2, 3, all=True, negate=negate),
                self.kls(1, 2, 3, all=True, negate=negate))
            self.assertNotEqual(
                self.kls(1, 2, all=True, negate=negate),
                self.kls(1, 2, 3, all=True, negate=negate))
            self.assertNotEqual(
                self.kls(1, 2, 3, all=False, negate=negate),
                self.kls(1, 2, 3, all=True, negate=negate))


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
