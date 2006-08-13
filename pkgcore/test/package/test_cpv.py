# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from twisted.trial import unittest
from pkgcore.package import cpv, errors


class CpvTest(unittest.TestCase):
	
	kls = staticmethod(cpv.native_CPV)
	
	goodcpv = ['dev-util/diffball', 'dev-util/diffball-0.7.1',
		'dev-util/diffball-cvs.2006']
	for x in ('alpha', 'beta', 'p', 'pre', 'rc'):
		goodcpv += ['dev-util/diffball-2.1_'+x, 'dev-util/diffball-2.1_%s12' % x]


	def test_cpv(self):
		for brokencpv in [
			'dev/one-2.8^&{/ILikeCookies',
			'two-2.5',
			'three',
			'dev-util/-diffball',
			'dev-util/diffball-cvs.cvs',
			'dev-util/diffball-2.2_alphaa',
			'dev-util/diffball-2.2_alpha_2.2_alpha',
			]:
			self.assertRaises(errors.InvalidCPV, self.kls, brokencpv)
		
		for goodcpv in self.goodcpv:
			self.kls(goodcpv)

if cpv.cpy_builtin:
	class CPY_CpvTest(CpvTest):
		kls = staticmethod(cpv.cpy_CPV)

