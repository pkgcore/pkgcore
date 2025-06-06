from functools import partial

import pytest

from pkgcore.restrictions import values

from .utils import TestRestriction


class SillyBool(values.base):
    """Extra stupid version of AlwaysBool to test base.force_{True,False}."""

    def __init__(self, negate=False):
        object.__setattr__(self, "negate", negate)

    def match(self, something):
        return not self.negate


class TestBase(TestRestriction):
    def test_force(self):
        self.assertMatches(SillyBool(negate=False), None, [None] * 3)
        self.assertNotMatches(SillyBool(negate=True), None, [None] * 3)


class TestGetAttr(TestRestriction):
    """Test bits of GetAttrRestriction that differ from PackageRestriction."""

    def test_force(self):
        # TODO we could do with both more tests and a more powerful
        # force_* implementation. This just tests if the function
        # takes the right number of arguments.

        # TODO test negate handling
        succeeds = values.GetAttrRestriction("test", values.AlwaysTrue)
        fails = values.GetAttrRestriction("test", values.AlwaysFalse)

        class Dummy:
            test = True

        dummy = Dummy()

        class FakePackage:
            """XXX this is vastly too minimal."""

            value = dummy

        pkg = FakePackage()

        args = [pkg, "value", dummy]
        self.assertForceTrue(succeeds, args)
        self.assertNotForceFalse(succeeds, args)
        self.assertNotForceTrue(fails, args)
        self.assertForceFalse(fails, args)


class TestStrRegex(TestRestriction):
    kls = values.StrRegex

    @pytest.mark.parametrize("negated", (True, False))
    def test_match(self, negated):
        self.assertMatches(
            self.kls("foo.*r", match=True, negate=negated),
            "foobar",
            [None, None, "foobar"],
            negated=negated,
        )
        self.assertNotMatches(
            self.kls("foo.*r", match=True, negate=negated),
            "afoobar",
            [None, None, "afoobar"],
            negated=negated,
        )

    @pytest.mark.parametrize("negated", (True, False))
    def test_search(self, negated):
        self.assertMatches(
            self.kls("foo.*r", negate=negated),
            "asdfoobar",
            [None, None, "asdfoobar"],
            negated=negated,
        )
        self.assertNotMatches(
            self.kls("foo.*r", negate=negated),
            "afobar",
            [None, None, "afobar"],
            negated=negated,
        )

    def test_case_sensitivity(self):
        self.assertNotMatches(self.kls("foo"), "FoO", ["FOo"] * 3)
        self.assertMatches(self.kls("foo", False), "FoO", ["fOo"] * 3)

    def test_str(self):
        assert "search spork" == str(self.kls("spork"))
        assert "not search spork" == str(self.kls("spork", negate=True))
        assert "match spork" == str(self.kls("spork", match=True))
        assert "not match spork" == str(self.kls("spork", match=True, negate=True))

    def test_repr(self):
        for restr, string in (
            (self.kls("spork"), "<StrRegex 'spork' search @"),
            (self.kls("spork", match=True), "<StrRegex 'spork' match @"),
            (self.kls("spork", negate=True), "<StrRegex 'spork' negated search @"),
        ):
            assert repr(restr).startswith(string), (restr, string)


class TestStrExactMatch(TestRestriction):
    if values.StrExactMatch is values.StrExactMatch:
        kls = values.StrExactMatch
    else:

        class kls(values.StrExactMatch, values.base):
            __slots__ = ()
            __inst_caching__ = True

            intersect = values._StrExact_intersect
            __repr__ = values._StrExact__repr__
            __str__ = values._StrExact__str__

    kls = staticmethod(kls)

    @pytest.mark.parametrize("negated", (True, False))
    def test_case_sensitive(self, negated):
        self.assertMatches(
            self.kls("package", negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )
        self.assertNotMatches(
            self.kls("Package", negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )

    @pytest.mark.parametrize("negated", (True, False))
    def test_case_insensitive(self, negated):
        # note that we explicitly test True/1, and False/0
        # we test 1/0, since bool protocol is supported for those kwds-
        # thus we verify it, more specifically we verify the cpy
        # support.
        self.assertMatches(
            self.kls("package", case_sensitive=True, negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )
        self.assertMatches(
            self.kls("package", case_sensitive=1, negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )
        self.assertMatches(
            self.kls("Package", case_sensitive=False, negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )
        self.assertMatches(
            self.kls("Package", case_sensitive=0, negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )

    @pytest.mark.parametrize("negate", (True, False))
    def test__eq__(self, negate):
        assert self.kls("rsync", negate=negate) == self.kls("rsync", negate=negate)
        for x in "Ca":
            assert self.kls("rsync", negate=negate) != self.kls(
                "rsyn" + x, negate=negate
            )
        assert self.kls("Rsync", case_sensitive=False, negate=negate) == self.kls(
            "rsync", case_sensitive=False, negate=negate
        )


class TestStrGlobMatch(TestRestriction):
    kls = values.StrGlobMatch

    @pytest.mark.parametrize("negated", (True, False))
    def test_matching(self, negated):
        self.assertMatches(
            self.kls("pack", negate=negated),
            "package",
            ["package"] * 3,
            negated=negated,
        )
        self.assertNotMatches(
            self.kls("pack", negate=negated), "apack", ["apack"] * 3, negated=negated
        )
        # case sensitive...
        self.assertMatches(
            self.kls("pAcK", case_sensitive=False, negate=negated),
            "pack",
            ["pack"] * 3,
            negated=negated,
        )
        self.assertNotMatches(
            self.kls("pAcK", case_sensitive=True, negate=negated),
            "pack",
            ["pack"] * 3,
            negated=negated,
        )

        # check prefix.
        self.assertMatches(
            self.kls("pAck", case_sensitive=False, prefix=True, negate=negated),
            "packa",
            ["packa"] * 3,
            negated=negated,
        )

        self.assertNotMatches(
            self.kls("pack", prefix=False, negate=negated),
            "apacka",
            ["apacka"] * 3,
            negated=negated,
        )

        self.assertMatches(
            self.kls("pack", prefix=False, negate=negated),
            "apack",
            ["apack"] * 3,
            negated=negated,
        )

        # daft, but verifies it's not doing contains.
        self.assertNotMatches(
            self.kls("pack", prefix=False, negate=negated),
            "apacka",
            ["apacka"] * 3,
            negated=negated,
        )

        self.assertNotMatches(
            self.kls("pack", prefix=False, case_sensitive=False, negate=negated),
            "aPacka",
            ["aPacka"] * 3,
            negated=negated,
        )

    def test__eq__(self):
        assert self.kls("rsync", prefix=False) != self.kls("rsync", prefix=True)
        for negate in (True, False):
            assert self.kls("rsync", negate=negate) == self.kls("rsync", negate=negate)
            for x in "Ca":
                assert self.kls("rsync", negate=negate) != self.kls(
                    "rsyn" + x, negate=negate
                )
            assert self.kls("Rsync", case_sensitive=False, negate=negate) != self.kls(
                "rsync", case_sensitive=True, negate=negate
            )
            assert self.kls("rsync", case_sensitive=False, negate=negate) != self.kls(
                "rsync", case_sensitive=True, negate=negate
            )
            assert self.kls("rsync", case_sensitive=False, negate=negate) != self.kls(
                "rsync", case_sensitive=True, negate=not negate
            )
        assert self.kls("rsync", negate=True) != self.kls("rsync", negate=False)


class TestEqualityMatch(TestRestriction):
    kls = staticmethod(values.EqualityMatch)

    @pytest.mark.parametrize("negated", (True, False))
    @pytest.mark.parametrize(
        ("x", "y", "ret"),
        (
            ("asdf", "asdf", True),
            ("asdf", "fdsa", False),
            (1, 1, True),
            (1, 2, False),
            (list(range(2)), list(range(2)), True),
            (list(range(2)), reversed(list(range(2))), False),
            (True, True, True),
            (True, False, False),
            (False, True, False),
        ),
    )
    def test_match(self, x, y, ret, negated):
        self.assertMatches(
            self.kls(x, negate=negated), y, [y] * 3, negated=(ret ^ (not negated))
        )

    def test__eq__(self):
        for negate in (True, False):
            assert self.kls("asdf", negate=negate) == self.kls("asdf", negate=negate)
            assert self.kls(1, negate=negate) != self.kls(2, negate=negate)
        assert self.kls("asdf", negate=True) != self.kls("asdf", negate=False)

    def test__hash__(self):
        def f(*args, **kwds):
            return hash(self.kls(*args, **kwds))

        assert f("dar") == f("dar")
        assert f("dar") == f("dar", negate=False)
        assert f("dar", negate=True) != f("dar", negate=False)
        assert f("dar", negate=True) == f("dar", negate=True)
        assert f("dar") != f("dar2")
        assert f("dar", negate=True) != f("dar2")


class TestContainmentMatch(TestRestriction):
    kls = staticmethod(partial(values.ContainmentMatch, disable_inst_caching=True))

    def test_match(self):
        for x, y, ret in (
            (list(range(10)), list(range(10)), True),
            (list(range(10)), [], False),
            (list(range(10)), set(range(10)), True),
            (set(range(10)), list(range(10)), True),
        ):
            for negated in (False, True):
                self.assertMatches(
                    self.kls(x, negate=negated, disable_inst_caching=True),
                    y,
                    [y] * 3,
                    negated=(ret == negated),
                )

        for negated in (False, True):
            # intentionally differing for the force_* args; slips in
            # an extra data set for testing.
            self.assertMatches(
                self.kls(range(10), match_all=True, negate=negated),
                list(range(20)),
                [list(range(10))] * 3,
                negated=negated,
            )
            self.assertNotMatches(
                self.kls(range(10), match_all=True, negate=negated),
                list(range(5)),
                [list(range(5))] * 3,
                negated=negated,
            )

        self.assertNotMatches(self.kls("asdf"), "fdsa", ["fdas"] * 3)
        self.assertMatches(self.kls("asdf"), "asdf", ["asdf"] * 3)
        self.assertMatches(self.kls("asdf"), "asdffdsa", ["asdffdsa"] * 3)
        self.assertMatches(self.kls("b"), "aba", ["aba"] * 3)

    @pytest.mark.parametrize("negate", (True, False))
    def test__eq__(self, negate):
        assert self.kls(range(100), negate=negate) == self.kls(
            range(100), negate=negate
        ), f"range(100), negate={negate}"
        assert self.kls("1", negate=not negate) != self.kls("1", negate=negate)
        assert self.kls((1, 2, 3), match_all=True, negate=negate) == self.kls(
            (1, 2, 3), match_all=True, negate=negate
        )
        assert self.kls((1, 2), match_all=True, negate=negate) != self.kls(
            (1, 2, 3), match_all=True, negate=negate
        )
        assert self.kls([1, 2, 3], match_all=False, negate=negate) != self.kls(
            [1, 2, 3], match_all=True, negate=negate
        )


class TestFlatteningRestriction:
    @pytest.mark.parametrize("negate", (True, False))
    def test_basic(self, negate):
        inst = values.FlatteningRestriction(
            tuple, values.AnyMatch(values.EqualityMatch(None)), negate=negate
        )
        assert not negate == inst.match([7, 8, [9, None]])
        assert negate == inst.match([7, 8, (9, None)])
        # Just check this does not raise
        assert str(inst)
        assert repr(inst)


class TestFunctionRestriction:
    @pytest.mark.parametrize("negate", (True, False))
    def test_basic(self, negate):
        def yes(val):
            return True

        def no(val):
            return False

        yes_restrict = values.FunctionRestriction(yes, negate=negate)
        no_restrict = values.FunctionRestriction(no, negate=negate)
        assert not negate == yes_restrict.match(7)
        assert negate == no_restrict.match(7)
        for restrict in yes_restrict, no_restrict:
            # Just check this does not raise
            assert str(restrict)
            assert repr(restrict)


class TestAnyMatch:
    # Most of AnyMatch is tested through test_restriction.

    def test_force(self):
        restrict = values.AnyMatch(values.AlwaysTrue)
        assert restrict.force_True(None, None, list(range(2)))
        assert not restrict.force_False(None, None, list(range(2)))
