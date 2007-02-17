# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2


from pkgcore.test import TestCase
from pkgcore.restrictions.packages import AlwaysTrue, AlwaysFalse
from pkgcore.restrictions.delegated import delegate

class Test_delegate(TestCase):

    kls = delegate

    def test_it(self):
        self.assertRaises(TypeError, self.kls, None, None)
        y = True
        l = []
        def f(x, mode):
            l.append(mode)
            if mode == 'force_false':
                return not y
            return y

        for negate in (False, True):
            def assertIt(got, expected):
                self.assertEqual(got, expected,
                    msg="got=%r, expected=%r, negate=%r, y=%r" %
                        (got, expected, negate, y))
            y = True
            l[:] = []
            o = self.kls(f, negate=negate)
            assertIt(o.match(None), not negate)
            assertIt(o.force_true(None), not negate)
            assertIt(o.force_false(None), negate)

            y = False
            assertIt(o.match(None), negate)
            assertIt(o.force_true(None), negate)
            assertIt(o.force_false(None), not negate)
            if negate:
                assertIt(l, ['match', 'force_false', 'force_true',
                    'match', 'force_false', 'force_true'])
            else:
                assertIt(l, ['match', 'force_true', 'force_false',
                    'match', 'force_true', 'force_false'])

    def test_caching(self):
        self.assertFalse(self.kls.inst_caching, False)
