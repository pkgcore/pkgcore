# Copyright: 2007-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.test import TestCase
from snakeoil.test import mk_cpy_loadable_testcase
from pkgcore.ebuild import misc
from pkgcore.restrictions import packages

AlwaysTrue = packages.AlwaysTrue
AlwaysFalse = packages.AlwaysFalse


class base(TestCase):

    def assertState(self, obj, defaults=[], freeform=[], atoms=[]):
        self.assertEqual(sorted(obj.defaults), sorted(defaults),
            reflective=False)
        self.assertEqual(sorted(obj.freeform), sorted(freeform),
            reflective=False)
        atoms_dict = dict((a[0].key, (a, a[1])) for a in atoms)
        self.assertEqual(sorted(obj.atoms), sorted(atoms_dict))
        for k, v in obj.atoms.iteritems():
            l1 = sorted((x[0], list(x[1])) for x in v)
            l2 = sorted((x[0], list(x[1])) for x, y in
                atoms_dict[k])
            self.assertEqual(l1, l2, msg="for %r atom, got %r, expected %r"
                % (k, l1, l2))


class test_collapsed_restrict_to_data(base):

    kls = misc.collapsed_restrict_to_data

    def test_defaults(self):
        srange = map(str, xrange(100))
        self.assertState(self.kls([(AlwaysTrue, srange)]),
            defaults=srange)
        # ensure AlwaysFalse is ignored.
        self.assertState(self.kls([(AlwaysFalse, srange)]))
        # check always ordering.
        self.assertState(self.kls([(AlwaysTrue, ['x'])],
            [(AlwaysTrue, ['x', 'y']), (AlwaysTrue, ['-x'])]),
            defaults=['y'])


class test_incremental_license_expansion(TestCase):

    def test_it(self):
        raise AssertionError()

    test_it.todo = "implement this..."


class test_native_incremental_expansion(TestCase):
    f = staticmethod(misc.native_incremental_expansion)

    def test_it(self):
        s = set("ab")
        self.f(s, ("-a", "b", "-b", "-b", "c"))
        self.assertEqual(sorted(s), ["c"])
        self.assertRaises(ValueError,
            self.f, set(), '-')

    def test_non_finalized(self):
        s = set("ab")
        self.f(s, ("-a", "b", "-b", "c", "c"),
            finalize=False)
        self.assertEqual(sorted(s), ["-a", "-b", "c"])

    def test_starred(self):
        s = set('ab')
        self.f(s, ('c', '-*', 'd'))
        self.assertEqual(sorted(s), ['d'])

class test_CPY_incremental_expansion(test_native_incremental_expansion):
    if misc.incremental_expansion == misc.native_incremental_expansion:
        skip = "CPy extension not available"
    f = staticmethod(misc.incremental_expansion)

test_cpy_used = mk_cpy_loadable_testcase('pkgcore.ebuild._misc',
    "pkgcore.ebuild.misc", "incremental_expansion", "incremental_expansion")


class TestIncrementalsDict(TestCase):
    kls = misc.IncrementalsDict

    def assertContents(self, mapping1, mapping2):
        self.assertEqual(sorted(mapping1.iteritems()), sorted(mapping2.iteritems()))

    def test_behaviour(self):
        d = self.kls(frozenset("i1 i2".split()), a1="1", i1="1")
        expected = {"a1":"1", "i1":"1"}
        self.assertContents(d, expected)
        d["a1"] = "2"
        expected["a1"] = "2"
        self.assertContents(d, expected)
        d["i1"] = "2"
        expected["i1"] = "1 2"
        self.assertContents(d, expected)
        del d["i1"]
        del expected["i1"]
        self.assertContents(d, expected)
