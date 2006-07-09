# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest
from pkgcore.package import cpv, errors


class CpvTest(unittest.TestCase):

	def test_cpv(self):
		for brokencpv in [
			'dev/one-2.8^&{/ILikeCookies',
			'two-2.5',
			'three',
			]:
			self.assertRaises(errors.InvalidCpv, cpv.CPV, brokencpv)
