import pytest
from pkgcore.ebuild import misc
from pkgcore.restrictions import packages
from snakeoil.test import TestCase

AlwaysTrue = packages.AlwaysTrue
AlwaysFalse = packages.AlwaysFalse


class base(TestCase):

    def assertState(self, obj, defaults=[], freeform=[], atoms=[]):
        self.assertEqual(sorted(obj.defaults), sorted(defaults),
            reflective=False)
        self.assertEqual(sorted(obj.freeform), sorted(freeform),
            reflective=False)
        atoms_dict = {a[0].key: (a, a[1]) for a in atoms}
        self.assertEqual(sorted(obj.atoms), sorted(atoms_dict))
        for k, v in obj.atoms.items():
            l1 = sorted((x[0], list(x[1])) for x in v)
            l2 = sorted((x[0], list(x[1])) for x, y in
                atoms_dict[k])
            self.assertEqual(l1, l2, msg=f"for {k!r} atom, got {l1!r}, expected {l2!r}")


class test_collapsed_restrict_to_data(base):

    kls = misc.collapsed_restrict_to_data

    def test_defaults(self):
        srange = list(map(str, range(100)))
        self.assertState(self.kls([(AlwaysTrue, srange)]),
            defaults=srange)
        # ensure AlwaysFalse is ignored.
        self.assertState(self.kls([(AlwaysFalse, srange)]))
        # check always ordering.
        self.assertState(self.kls([(AlwaysTrue, ['x'])],
            [(AlwaysTrue, ['x', 'y']), (AlwaysTrue, ['-x'])]),
            defaults=['y'])


# class test_incremental_license_expansion(TestCase):
#
#     def test_it(self):
#         raise AssertionError()
#
#     test_it.todo = "implement this..."


class test_incremental_expansion(TestCase):
    f = staticmethod(misc.incremental_expansion)

    def test_it(self):
        s = set("ab")
        self.f(("-a", "b", "-b", "-b", "c"), orig=s)
        self.assertEqual(sorted(s), ["c"])
        self.assertRaises(ValueError, self.f, set(), '-')

    def test_non_finalized(self):
        s = set("ab")
        self.f(("-a", "b", "-b", "c", "c"), orig=s, finalize=False)
        self.assertEqual(sorted(s), ["-a", "-b", "c"])

    def test_starred(self):
        s = set('ab')
        self.f(('c', '-*', 'd'), orig=s)
        self.assertEqual(sorted(s), ['d'])


class TestIncrementalsDict(TestCase):
    kls = misc.IncrementalsDict

    def assertContents(self, mapping1, mapping2):
        self.assertEqual(sorted(mapping1.items()), sorted(mapping2.items()))

    def test_behaviour(self):
        d = self.kls(frozenset("i1 i2".split()), a1="1", i1="1")
        expected = {"a1":"1", "i1":"1"}
        self.assertContents(d, expected)
        d["a1"] = "2"
        expected["a1"] = "2"
        self.assertContents(d, expected)
        self.assertTrue(d)
        self.assertEqual(sorted(d), ["a1", "i1"])
        self.assertLen(d, 2)
        d["i1"] = "2"
        expected["i1"] = "1 2"
        self.assertContents(d, expected)
        del d["a1"]
        del expected["a1"]
        self.assertContents(d, expected)
        self.assertEqual(d['i1'], "1 2")
        self.assertTrue(d)
        self.assertEqual(sorted(d), ["i1"])
        d.clear()
        self.assertFalse(d)
        self.assertLen(d, 0)


@pytest.mark.parametrize('expected,source,target',
    [('../../bin/foo', '/bin/foo', '/usr/bin/foo'),
     ('../../../doc/foo-1', '/usr/share/doc/foo-1', '/usr/share/texmf-site/doc/fonts/foo'),
     ('../../opt/bar/foo', '/opt/bar/foo', '/usr/bin/foo'),
     ('../c/d/e', '/a/b/c/d/e', 'a/b/f/g'),
     ('b/f', '/a/b///./c/d/../e/..//../f', '/a/././///g/../h'),
     ('../h', '/a/././///g/../h', '/a/b///./c/d/../e/..//../f'),
     ('.', '/foo', '/foo/bar'),
     ('..', '/foo', '/foo/bar/baz'),
     ('../../fo . o/b ar', '/fo . o/b ar', '/baz / qu .. ux/qu x'),
     (r'../../f"o\o/b$a[]r', r'/f"o\o/b$a[]r', r'/ba\z/qu$u"x/qux'),
     ])
def test_get_relative_dosym_target(expected, source, target):
    assert expected == misc.get_relative_dosym_target(source, target)
