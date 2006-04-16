# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.graph.choice_point import choice_point
from pkgcore.restrictions.boolean import AndRestriction, OrRestriction

class fake_package(object):
	def __init__(self, marker, depends=AndRestriction(), rdepends=AndRestriction(), provides=AndRestriction()):
		self.depends = depends
		self.rdepends = rdepends
		self.provides = provides
		self.marker = marker

class TestChoicePoint(unittest.TestCase):

	@staticmethod
	def gen_choice_point():
		return choice_point("asdf", [
			fake_package(1, OrRestriction("ordep1", "ordep2", "dependsordep"), 
				AndRestriction(OrRestriction("ordep1", "andordep2"), "anddep1", "anddep2", "pkg1and")),
			fake_package(2, AndRestriction("anddep1", "anddep2"), 
				OrRestriction("or1", "or2"))])

	def test_current_pkg(self):
		c = self.gen_choice_point()
		self.assertEqual(c.current_pkg.marker, 1)
		atoms,p=c.reduce_atoms("pkg1and")
		self.assertEqual(c.current_pkg.marker, 2)

	def test_reduce(self):
		c = self.gen_choice_point()
		self.assertEqual(c.current_pkg.marker, 1)
		self.assertEqual(c.reduce_atoms("dependsordep")[0], set())
		self.assertEqual(c.reduce_atoms("ordep2")[0], set())
		self.assertEqual(c.reduce_atoms("ordep1")[0], set(["or1"]))
		self.assertEqual(c.current_pkg.marker, 2)

