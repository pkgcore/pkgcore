# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.repository.prototype import tree
from twisted.trial import unittest
from pkgcore.restrictions import packages, values
from pkgcore.package.atom import atom
from pkgcore.package.cpv import CPV
from pkgcore.util.currying import pre_curry
from pkgcore.util.mappings import OrderedDict

rev_sorted = pre_curry(sorted, reverse=True)

class SimpleTree(tree):
	package_class = CPV
	def __init__(self, cpv_dict):
		self.cpv_dict = cpv_dict
		tree.__init__(self)
	
	def _get_categories(self, *arg):
		if arg:
			return ()
		return tuple(self.cpv_dict.iterkeys())

	def _get_packages(self, category):
		return tuple(self.cpv_dict[category].iterkeys())

	def _get_versions(self, cp_key):
		cat, pkg = cp_key.rsplit("/", 1)
		return tuple(self.cpv_dict[cat][pkg])


class TestPrototype(unittest.TestCase):
	
	def setUp(self):
		# we an orderreddict here specifically to trigger any sorter related bugs
		d = {"dev-util":{"diffball":["1.0", "0.7"], "bsdiff":["0.4.1", "0.4.2"]},
			"dev-lib":{"fake":["1.0", "1.0-r1"]}}
		self.repo = SimpleTree(OrderedDict((k, d[k]) for k in sorted(d, reverse=True)))

	def test_internal_lookups(self):
		self.assertEqual(sorted(self.repo.categories), sorted(["dev-lib", "dev-util"]))
		self.assertEqual(sorted(self.repo.packages), sorted(["dev-util/diffball", "dev-util/bsdiff", "dev-lib/fake"]))
		self.assertEqual(sorted(self.repo.versions), sorted(["dev-util/diffball-1.0", "dev-util/diffball-0.7",
			"dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2", "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1"]))

	def test_simple_query(self):
		a = atom("=dev-util/diffball-1.0")
		self.repo.match(a)
		self.assertTrue(self.repo.match(a))
		self.assertFalse(self.repo.match(atom("dev-util/monkeys_rule")))

	def test_identify_candidates(self):
		self.assertRaises(TypeError, self.repo.match, ("asdf"))
		rc = packages.PackageRestriction("category", values.StrExactMatch("dev-util"))
		self.assertEqual(sorted(set(x.package for x in self.repo.itermatch(rc))),
			sorted(["diffball", "bsdiff"]))
		rp = packages.PackageRestriction("package", values.StrExactMatch("diffball"))
		self.assertEqual(list(x.version for x in self.repo.itermatch(rp, sorter=sorted)), ["0.7", "1.0"])
		self.assertEqual(self.repo.match(packages.OrRestriction(rc, rp), sorter=sorted),
			sorted(CPV(x) for x in ("dev-util/diffball-0.7", "dev-util/diffball-1.0", "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2")))
		self.assertEqual(sorted(self.repo.itermatch(packages.AndRestriction(rc, rp))),
			sorted(CPV(x) for x in ("dev-util/diffball-0.7", "dev-util/diffball-1.0")))
		self.assertEqual(sorted(self.repo), self.repo.match(packages.AlwaysTrue, sorter=sorted))
		self.assertEqual(sorted(self.repo), self.repo.match(packages.OrRestriction(rc, rp), sorter=sorted))
		rc2 = packages.PackageRestriction("category", values.StrExactMatch("dev-lib"))
		self.assertEqual(sorted(self.repo.itermatch(packages.AndRestriction(rp, rc2))), sorted([]))

		# note this mixes a category level match, and a pkg level match.  they *must* be treated as an or.
		self.assertEqual(sorted(self.repo.itermatch(packages.OrRestriction(rp, rc2))),
			sorted(CPV(x) for x in ("dev-util/diffball-0.7", "dev-util/diffball-1.0", "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

		# this is similar to the test above, but mixes a cat/pkg candidate with a pkg candidate
		rp2 = packages.PackageRestriction("package", values.StrExactMatch("fake"))
		r = packages.OrRestriction(atom("dev-util/diffball"), rp2)
		self.assertEqual(sorted(self.repo.itermatch(r)),
			sorted(CPV(x) for x in ("dev-util/diffball-0.7", "dev-util/diffball-1.0", "dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))

		self.assertEqual(sorted(self.repo.itermatch(packages.OrRestriction(packages.AlwaysTrue, rp2))),
			sorted(CPV(x) for x in ("dev-util/diffball-0.7", "dev-util/diffball-1.0", "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
			"dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))


	def test_iter(self):
		self.assertEqual(sorted(self.repo), sorted(CPV(x) for x in 
			("dev-util/diffball-1.0", "dev-util/diffball-0.7", "dev-util/bsdiff-0.4.1", "dev-util/bsdiff-0.4.2",
			"dev-lib/fake-1.0", "dev-lib/fake-1.0-r1")))
