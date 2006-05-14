# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.graph.choice_point import choice_point
from pkgcore.restrictions.boolean import AndRestriction, OrRestriction

class fake_package(object):
	def __init__(self, **kwds):
		for k,v in (("depends", AndRestriction()),
			("rdepends", AndRestriction()),
			("provides", AndRestriction()),
			("slot", 0), ("key", None), ("marker", None)):
			setattr(self, k, kwds.get(k, v))

class TestChoicePoint(unittest.TestCase):

	@staticmethod
	def gen_choice_point():
		return choice_point("asdf", [
			fake_package(marker=1, depends=OrRestriction("ordep1", "ordep2", "dependsordep"),
				rdepends=AndRestriction(OrRestriction("ordep1", "andordep2"), "anddep1", "anddep2", "pkg1and")),
			fake_package(marker=2, depends=AndRestriction("anddep1", "anddep2"),
				rdepends=OrRestriction("or1", "or2"))])

	def test_depends_rdepends_stepping(self):
		c = self.gen_choice_point()
		self.assertEqual(c.depends, ("ordep1",))
		self.assertEqual(sorted(c.rdepends), sorted(["ordep1", "anddep1", "anddep2", "pkg1and"]))
		c.reduce_atoms("ordep1")
		self.assertEqual(c.depends, ("ordep2",))
		self.assertEqual(sorted(c.rdepends), sorted(["andordep2", "anddep1", "anddep2", "pkg1and"]))
		c.reduce_atoms("pkg1and")
		c.reduce_atoms("or1")
		self.assertEqual(c.rdepends, ("or2",))

	def test_current_pkg(self):
		c = self.gen_choice_point()
		self.assertEqual(c.current_pkg.marker, 1)
		atoms,p = c.reduce_atoms("pkg1and")
		self.assertEqual(c.current_pkg.marker, 2)

	def test_reduce(self):
		c = self.gen_choice_point()
		self.assertEqual(c.current_pkg.marker, 1)
		self.assertEqual(c.reduce_atoms("dependsordep")[0], set())
		self.assertEqual(c.reduce_atoms("ordep2")[0], set())
		self.assertEqual(c.reduce_atoms("ordep1")[0], set(["or1"]))
		self.assertEqual(c.current_pkg.marker, 2)
		c = self.gen_choice_point()
		self.assertEqual(c.reduce_atoms("anddep2")[0], set(["ordep1", "ordep1", "anddep1", "anddep2", "pkg1and"]))
		c = self.gen_choice_point()
		c.reduce_atoms("anddep1")
		self.assertRaises(IndexError, lambda :c.depends)

	def test_nonzero(self):
		c = self.gen_choice_point()
		self.assertEqual(bool(c), True)
		self.assertEqual(c.current_pkg.marker, 1)
		c.reduce_atoms("anddep1")
		self.assertEqual(bool(c), False)
