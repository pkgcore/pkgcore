from pkgcore.restrictions.delegated import delegate
from pkgcore.test import TestRestriction


class Test_delegate(TestRestriction):

    kls = delegate

    def test_it(self):
        self.assertRaises(TypeError, self.kls, None, None)
        y = True
        l = []
        def f(x, mode):
            l.append(mode)
            if mode == 'force_False':
                return not y
            return y

        for negated in (False, True):
            def assertIt(got, expected):
                self.assertEqual(
                    got, expected,
                    msg=f"got={got!r}, expected={expected!r}, negate={negated!r}")
            y = True
            l[:] = []
            o = self.kls(f, negate=negated)
            self.assertMatches(o, [None], negated=negated)

            y = False
            self.assertNotMatches(o, [None], negated=negated)

            if negated:
                assertIt(l, ['match', 'force_False', 'force_True',
                    'match', 'force_False', 'force_True'])
            else:
                assertIt(l, ['match', 'force_True', 'force_False',
                    'match', 'force_True', 'force_False'])

    def test_caching(self):
        self.assertFalse(self.kls.inst_caching, False)
