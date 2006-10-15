# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild import ebuild_src
from pkgcore.ebuild import const

class TestBase(TestCase):
    
    def get_pkg(self, data, cpv='dev-util/diffball-0.1-r1', repo=None):
        o = ebuild_src.base(repo, cpv)
        object.__setattr__(o, 'data', data)
        return o
    
    def test_init(self):
        o = self.get_pkg({}, cpv='dev-util/diffball-0.1-r1')
        self.assertEqual(o.category, 'dev-util')
        self.assertEqual(o.package, 'diffball')
        self.assertEqual(o.fullver, '0.1-r1')
        self.assertEqual(o.PN, 'diffball')
        self.assertEqual(o.P, 'diffball-0.1')
        self.assertEqual(o.PF, 'diffball-0.1-r1')
        self.assertEqual(o.PR, 1)
        self.assertEqual(self.get_pkg({}, 'dev-util/diffball-0.1').PR,
            0)
    
    def test_license(self):
        o = self.get_pkg({'LICENSE':'GPL2 FOON'})
        self.assertEqual(list(o.license), ['GPL2', 'FOON'])

    def test_description(self):
        o = self.get_pkg({'DESCRIPTION':' foon\n asdf '})
        self.assertEqual(o.description, 'foon\n asdf')

    def test_iuse(self):
        o = self.get_pkg({'IUSE':'build pkg foon'})
        self.assertEqual(list(o.iuse), ['build', 'pkg', 'foon'])

    def test_homepage(self):
        o = self.get_pkg({'HOMEPAGE': ' http://slashdot/ '})
        self.assertEqual(o.homepage, 'http://slashdot/')
    
    def test_slot(self):
        o = self.get_pkg({'SLOT': '0'})
        self.assertEqual(o.slot, '0')
        self.assertRaises(ValueError, getattr, self.get_pkg({'SLOT':''}), 
            'slot')
    
    def test_restrict(self):
        o = self.get_pkg({'RESTRICT': 'strip boobs strip'})
        self.assertEqual(*map(sorted, (o.restrict, ['strip', 'boobs'])))
        self.assertEqual(self.get_pkg({'RESTRICT':'nofetch'}).restrict,
            ('fetch',))
    
    def test_eapi(self):
        self.assertEqual(self.get_pkg({'EAPI': '0'}).eapi, 0)
        self.assertEqual(self.get_pkg({'EAPI': ''}).eapi, 0)
        self.assertEqual(self.get_pkg({'EAPI': 'foon'}).eapi, 
            const.unknown_eapi)
    
    def test_keywords(self):
        self.assertEqual(list(self.get_pkg({'KEYWORDS':''}).keywords), [])
        self.assertEqual(sorted(self.get_pkg(
            {'KEYWORDS':'x86 amd64'}).keywords),
            sorted(['x86', 'amd64']))
#    def test_eapi(self):
        
