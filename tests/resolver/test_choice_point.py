from snakeoil.test import TestCase

from pkgcore.resolver.choice_point import choice_point
from pkgcore.restrictions.boolean import AndRestriction, OrRestriction


class fake_package:

    def __init__(self, **kwds):
        for k, v in (
                ("bdepend", AndRestriction()),
                ("depend", AndRestriction()),
                ("rdepend", AndRestriction()),
                ("pdepend", AndRestriction()),
                ("slot", 0),
                ("key", None),
                ("marker", None)):
            setattr(self, k, kwds.get(k, v))

class TestChoicePoint(TestCase):

    @staticmethod
    def gen_choice_point():
        return choice_point("asdf", [
            fake_package(marker=1, depend=OrRestriction(
                        "ordep1", "ordep2", "dependordep"),
                rdepend=AndRestriction(
                        OrRestriction("ordep1", "andordep2"),
                        "anddep1", "anddep2", "pkg1and"),
                pdepend=OrRestriction("prdep1", "or3")),
            fake_package(marker=2, depend=AndRestriction(
                        "anddep1", "anddep2"),
                rdepend=OrRestriction("or1", "or2"),
                pdepend=OrRestriction("prdep1", "or3"))])

    def test_depend_rdepend_stepping(self):
        c = self.gen_choice_point()
        self.assertEqual(c.depend, [["ordep1", "ordep2", "dependordep"]])
        self.assertEqual(
            sorted(c.rdepend),
            sorted([['anddep1'], ['anddep2'], ['ordep1', 'andordep2'],
                    ['pkg1and']]))
        c.reduce_atoms("ordep1")
        self.assertEqual(c.depend, [['ordep2', 'dependordep']])
        self.assertEqual(
            sorted(c.rdepend),
            sorted([['anddep1'], ['anddep2'], ['andordep2'], ['pkg1and']]))
        c.reduce_atoms("pkg1and")
        c.reduce_atoms("or1")
        self.assertEqual(c.rdepend, [["or2"]])
        c.reduce_atoms("prdep1")
        self.assertEqual(c.depend, [['anddep1'], ['anddep2']])
        self.assertEqual(c.pdepend, [["or3"]])
        c.reduce_atoms("or3")
        self.assertRaises(IndexError, lambda: c.depend)

    def test_current_pkg(self):
        c = self.gen_choice_point()
        self.assertEqual(c.current_pkg.marker, 1)
        c.reduce_atoms("pkg1and")
        self.assertEqual(c.current_pkg.marker, 2)

    def test_reduce(self):
        c = self.gen_choice_point()
        self.assertEqual(c.current_pkg.marker, 1)
        self.assertEqual(c.reduce_atoms("dependordep"), False)
        self.assertEqual(c.reduce_atoms("ordep2"), False)
        self.assertEqual(c.reduce_atoms("ordep1"), True)
        self.assertEqual(c.current_pkg.marker, 2)
        c = self.gen_choice_point()
        self.assertEqual(c.reduce_atoms("anddep2"), True)
        c = self.gen_choice_point()
        c.reduce_atoms("anddep1")
        self.assertRaises(IndexError, lambda: c.depend)
        self.assertRaises(IndexError, lambda: c.rdepend)
        self.assertRaises(IndexError, lambda: c.pdepend)

    def test_nonzero(self):
        c = self.gen_choice_point()
        self.assertEqual(bool(c), True)
        self.assertEqual(c.current_pkg.marker, 1)
        c.reduce_atoms("anddep1")
        self.assertEqual(bool(c), False)
