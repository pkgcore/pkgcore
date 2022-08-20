from functools import partial

import pytest

from pkgcore.restrictions import restriction

from .utils import TestRestriction


class SillyBool(restriction.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""

    __slots__ = ('negate',)

    def __init__(self, negate=False):
        object.__setattr__(self, 'negate', negate)

    def match(self, *args, **kwargs):
        return not self.negate


class TestBase(TestRestriction):

    bool_kls = SillyBool

    def test_base(self):
        base = restriction.base()
        assert len(base) == 1
        # Just check repr and str do not raise
        assert str(base)
        assert repr(base)
        assert hash(base)
        with pytest.raises(NotImplementedError):
            base.match()

    def test_it(self):
        true = self.bool_kls(negate=False)
        false = self.bool_kls(negate=True)
        args = [None]

        self.assertMatch(true, args[0])
        self.assertForceTrue(true, args)
        self.assertNotForceFalse(true, args)

        self.assertNotMatch(false, args[0])
        self.assertNotForceTrue(false, args)
        self.assertForceFalse(false, args)


class TestAlwaysBool(TestRestriction):

    bool_kls = partial(restriction.AlwaysBool, 'foo')

    def test_true(self):
        true_r = self.bool_kls(True)
        false_r = self.bool_kls(False)
        self.assertMatch(true_r, false_r)
        self.assertForceTrue(true_r, false_r)
        self.assertNotForceFalse(true_r, false_r)

        self.assertNotMatch(false_r, true_r)
        self.assertNotForceTrue(false_r, true_r)
        self.assertForceFalse(false_r, true_r)

        assert str(true_r) == "always 'True'"
        assert str(false_r) == "always 'False'"
        assert hash(true_r) != hash(false_r)
        assert hash(true_r) == hash(self.bool_kls(True))
        assert hash(false_r) == hash(self.bool_kls(False))
        assert true_r == self.bool_kls(True)
        assert false_r == self.bool_kls(False)
        assert true_r != false_r


class NoneMatch(restriction.base):

    """Only matches None."""

    __slots__ = ()

    def match(self, val):
        return val is None

    def __repr__(self):
        return '<NoneMatch>'

    def __str__(self):
        return 'NoneMatch'


class TestAnyMatch(TestRestriction):

    def test_basic(self):
        for negate in (False, True):
            inst = restriction.AnyMatch(NoneMatch(), 'spork', negate=negate)
            self.assertMatch(inst, ['spork', None], negated=negate)
            self.assertNotMatch(inst, ['spork'], negated=negate)
            self.assertNotMatch(inst, (), negated=negate)

            # just test these do not traceback
            assert repr(inst)
            assert str(inst)
