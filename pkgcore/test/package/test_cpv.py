# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest
from pkgcore.package import cpv, errors


class native_CpvTest(unittest.TestCase):
	
	kls = staticmethod(cpv.native_CPV)
	good_cats = ["dev-util", "asdf", "dev+", "dev-util+", "DEV-UTIL", "aaa0", "zzz9", "aaa-0", "bbb-9"]
	bad_cats  = ["dev.util", "dev_", ""]
	good_pkgs = ["diffball", "a9", "a9+", "a-100dpi", "a-cvs"]
	bad_pkgs  = [""]
	good_vers = ["1", "2.3.4", "2.3.4a", "02.3", "2.03"]
	good_vers = ["cvs.%s" % x for x in good_vers] + good_vers
	bad_vers  = ["2.3a.4", "2.a.3", "2.3_"]
	simple_good_sufs = ["_alpha", "_beta", "_pre", "_p"]
	good_sufs = simple_good_sufs + ["%s1" % x for x in simple_good_sufs] + ["%s932" % x for x in simple_good_sufs]
	l = len(good_sufs)
	good_sufs = good_sufs + [good_sufs[x] + good_sufs[l - x - 1] for x in xrange(l)]
	del l
	bad_sufs  = ["_a", "_9", "_"]
	del simple_good_sufs
	good_revs = ["-r1", "-r300",""]
	bad_revs = ["-r", "-ra", "-r", "-R1"]

	def test_simple_key(self):
		for src in [["dev-util/diffball-0.7.1", "dev-util/diffball"], 
			["dev-util/diffball"], 
			["dev-perl/mod_perl"], 
			["dev-perl/mod_p"],
			["dev-perl/mod-p"],
			["dev-perl/mod-p-1", "dev-perl/mod-p"],]:
			if len(src) == 1:
				key = src[0]
			else:
				key = src[1]
			self.assertEqual(self.kls(src[0]).key, key)

	def test_parsing(self):
		for cat_ret, cats in [[False, self.good_cats], [True, self.bad_cats]]:
			for cat in cats:
				self.process_cat(cat_ret, cat)
	locals()["test_parsing (may take minutes)"] = test_parsing
	del test_parsing
	
	def process_cat(self, ret, cat):
		for pkg_ret, pkgs in [[False, self.good_pkgs], [True, self.bad_pkgs]]:
			for pkg in pkgs:
				self.process_pkg(ret or pkg_ret, cat, pkg)

	def process_pkg(self, ret, cat, pkg):
		if ret:
			self.assertRaises(errors.InvalidCPV, self.kls, "%s/%s" % (cat, pkg))
		else:
			c = self.kls("%s/%s" % (cat, pkg))
			self.assertEqual(c.category, cat)
			self.assertEqual(c.package, pkg)
			self.assertEqual(c.key, "%s/%s" % (cat,pkg))
			self.assertEqual(c.revision, None)
			self.assertEqual(c.version, None)
			self.assertEqual(c.fullver, None)
		for rev_ret, revs in [[False, self.good_revs], [True, self.bad_revs]]:
			for rev in revs:
				for ver_ret, vers in [[False, self.good_vers], [True, self.bad_vers]]:
					for ver in vers:
						self.process_ver(ret or ver_ret or rev_ret, cat, pkg, ver, rev)

	def process_ver(self, ret, cat, pkg, ver, rev):
		if ret:
			self.assertRaises(errors.InvalidCPV, self.kls, "%s/%s-%s%s" % (cat, pkg, ver, rev))
		else:
			c = self.kls("%s/%s-%s%s" % (cat, pkg, ver, rev))
			self.assertEqual(c.category, cat)
			self.assertEqual(c.package, pkg)
			self.assertEqual(c.key, "%s/%s" % (cat,pkg))
			if rev == "":
				self.assertEqual(c.revision, None)
			else:
				self.assertEqual(c.revision, int(rev.lstrip("-r")))
			self.assertEqual(c.version, ver)
			self.assertEqual(c.fullver, ver+rev)

		for suf in self.good_sufs:
			self.process_suf(ret, cat, pkg, ver + suf, rev)
			for bad_suf in self.bad_sufs:
				# double process, front and back.
				self.process_suf(True, cat, pkg, suf + bad_suf, rev)
				self.process_suf(True, cat, pkg, bad_suf + suf, rev)

		for suf in self.bad_sufs:
			# check standalone.
			self.process_suf(True, cat, pkg, ver+suf, rev)

	def process_suf(self, ret, cat, pkg, ver, rev):
		if ret:
			self.assertRaises(errors.InvalidCPV, self.kls, "%s/%s-%s%s" % (cat, pkg, ver, rev))
		else:
			c = self.kls("%s/%s-%s%s" % (cat, pkg, ver, rev))
			self.assertEqual(c.category, cat)
			self.assertEqual(c.package, pkg)
			self.assertEqual(c.key, "%s/%s" % (cat,pkg))
			if rev == "":
				self.assertEqual(c.revision, None)
			else:
				self.assertEqual(c.revision, int(rev.lstrip("-r")))
			self.assertEqual(c.version, ver)
			self.assertEqual(c.fullver, ver + rev)


if cpv.cpy_builtin:
	class CPY_CpvTest(native_CpvTest):
		kls = staticmethod(cpv.cpy_CPV)

