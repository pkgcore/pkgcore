import pytest

from pkgcore.restrictions.delegated import delegate

from .utils import TestRestriction


class Test_delegate(TestRestriction):
    kls = delegate

    def test_it(self):
        with pytest.raises(TypeError):
            self.kls(None, None)
        y = True
        l = []

        def f(x, mode):
            l.append(mode)
            if mode == "force_False":
                return not y
            return y

        for negated in (False, True):
            y = True
            l[:] = []
            o = self.kls(f, negate=negated)
            self.assertMatches(o, [None], negated=negated)

            y = False
            self.assertNotMatches(o, [None], negated=negated)

            if negated:
                assert l == [
                    "match",
                    "force_False",
                    "force_True",
                    "match",
                    "force_False",
                    "force_True",
                ]
            else:
                assert l == [
                    "match",
                    "force_True",
                    "force_False",
                    "match",
                    "force_True",
                    "force_False",
                ]

    def test_caching(self):
        def f(*args):
            return False

        assert self.kls(f) is not self.kls(f)
