# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild import ebuild_src, repo_objs
from pkgcore import fetch
from pkgcore.package import errors
from pkgcore.ebuild import const
from pkgcore.util.currying import post_curry
from pkgcore.util.lists import iflatten_instance

class test_base(TestCase):

    kls = ebuild_src.base

    def get_pkg(self, data=None, cpv='dev-util/diffball-0.1-r1', repo=None,
        pre_args=()):
        o = self.kls(*(list(pre_args) + [repo, cpv]))
        if data is not None:
            object.__setattr__(o, 'data', data)
        return o

    def make_parent(self, **methods):
        class kls:
            locals().update(methods)
        return kls()

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

    def test_ebuild(self):
        l = []
        def f(self, cpv):
            l.append(cpv)
            return 1
        c = self.make_parent(get_ebuild_src=f)
        o = self.get_pkg({}, repo=c)
        self.assertEqual(o.ebuild, 1)
        self.assertEqual(l, [o])

    def test_fetch_metadata(self):
        def f(self, cpv):
            return {'1':'2'}
        o = self.get_pkg(repo=self.make_parent(_get_metadata=f))
        self.assertEqual(o.data, {'1': '2'})


    def test_license(self):
        o = self.get_pkg({'LICENSE':'GPL2 FOON'})
        self.assertEqual(list(o.license), ['GPL2', 'FOON'])

    def test_description(self):
        o = self.get_pkg({'DESCRIPTION':' foon\n asdf '})
        self.assertEqual(o.description, 'foon\n asdf')

    def test_iuse(self):
        o = self.get_pkg({'IUSE':'build pkg foon'})
        self.assertEqual(sorted(o.iuse), ['build', 'foon', 'pkg'])

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

    def generic_check_depends(self, depset, attr, expected=None,
        data_name=None):
        if expected is None:
            expected = depset
        if data_name is None:
            data_name = attr.rstrip('s').upper()
        o = self.get_pkg({data_name:depset})
        self.assertEqual(str(getattr(o, attr)), expected)
        o = self.get_pkg({data_name:''})
        self.assertEqual(str(getattr(o, attr)), '')
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({data_name:'|| ( '}), attr)

    for x in ('depends', 'rdepends'):
        locals()['test_%s' % x] = post_curry(generic_check_depends,
            'dev-util/diffball || ( dev-util/foo x86? ( dev-util/bsdiff ) )',
             x)
    del x
    test_post_rdepends = post_curry(generic_check_depends,
        'dev-util/diffball x86? ( virtual/boo )',
        'post_rdepends', data_name='PDEPEND')

    test_provides = post_curry(generic_check_depends,
        'virtual/foo x86? ( virtual/boo )',
        'provides', expected='virtual/foo-0.1-r1 x86? ( virtual/boo-0.1-r1 )')

    def test_fetchables(self):
        l = []
        def f(self, cpv):
            l.append(cpv)
            return {'monkey.tgz': {}, 'boon.tgz': {}}
        repo = self.make_parent(_get_digests=f)
        parent = self.make_parent(_parent_repo=repo)
        # verify it does digest lookups...
        o = self.get_pkg({'SRC_URI':'http://foo.com/bar.tgz'}, repo=parent)
        self.assertRaises(errors.MetadataException, getattr, o, 'fetchables')
        self.assertEqual(l, [o])

        # basic tests;
        f = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz'},
             repo=parent).fetchables
        self.assertEqual(list(f[0].uri), ['http://foo.com/monkey.tgz'])
        self.assertEqual(f[0].filename, 'monkey.tgz')

        # verify it collapses multiple basenames down to the same.
        f = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz '
            'http://foo.com2/monkey.tgz'}, repo=parent).fetchables
        self.assertEqual(list(f[0].uri), ['http://foo.com/monkey.tgz',
            'http://foo.com2/monkey.tgz'])

        mirror = fetch.mirror(['http://boon.com/'], 'mirror1')
        parent = self.make_parent(_parent_repo=repo, mirrors={
            'mirror1': mirror})

        f = self.get_pkg({'SRC_URI': 'mirror://mirror1/foon/monkey.tgz'},
            repo=parent).fetchables
        self.assertEqual(list(f[0].uri), ['http://boon.com/foon/monkey.tgz'])

        # assert it bails if mirror doesn't exist.
        self.assertRaises(errors.MetadataException, getattr, self.get_pkg(
                {'SRC_URI':'mirror://mirror2/foon/monkey.tgz'},
                repo=parent), 'fetchables')

        parent = self.make_parent(_parent_repo=repo, default_mirrors=mirror)
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz'},
            repo=parent).fetchables
        self.assertEqual(list(f[0].uri), ['http://boon.com/monkey.tgz',
            'http://foo.com/monkey.tgz'])

        # test primaryuri...
        mirror2 = fetch.mirror(['http://boon2.com/'], 'default')
        parent = self.make_parent(_parent_repo=repo, default_mirrors=mirror,
            mirrors={'mirror1':mirror2})
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz '
            'mirror://mirror1/boon.tgz', 'RESTRICT':'primaryuri'},
            repo=parent).fetchables
        self.assertEqual(list(f[0].uri),
            ['http://foo.com/monkey.tgz', 'http://boon.com/monkey.tgz'])
        self.assertEqual(list(f[1].uri),
            ['http://boon2.com/boon.tgz', 'http://boon.com/boon.tgz'])
        self.assertEqual(len(f), 2)

        # restrict=mirror..
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz',
            'RESTRICT': 'mirror'}, repo=parent).fetchables
        self.assertEqual(list(f[0].uri),
            ['http://foo.com/monkey.tgz'])
        self.assertEqual(len(f), 1)

        # test uri for when there *is* no uri
        f = self.get_pkg({'SRC_URI': 'monkey.tgz'}, repo=parent).fetchables
        self.assertEqual(list(f[0].uri), [])


class test_package(test_base):

    kls = ebuild_src.package

    def get_pkg(self, *args, **kwds):
        kwds.setdefault("pre_args", (None,))
        return test_base.get_pkg(self, *args, **kwds)

    def test_init(self):
        test_base.test_init(self)
        o = self.get_pkg(pre_args=(1,))
        self.assertEqual(o._shared_pkg_data, 1)

    def test_mtime_(self):
        l = []
        def f(self, cpv):
            l.append(cpv)
            return 100l

        parent = self.make_parent(_get_ebuild_mtime=f)
        o = self.get_pkg(repo=parent)
        self.assertEqual(o._mtime_, 100l)
        self.assertEqual(l, [o])

    def make_shared_pkg_data(self, manifest=None, metadata_xml=None):
        return self.get_pkg(
            pre_args=(repo_objs.SharedPkgData(metadata_xml, manifest),))

    def generic_metadata_xml(self, attr):
        m = repo_objs.MetadataXml(None)
        object.__setattr__(m, "_"+attr, "foon")
        object.__setattr__(m, "_source", None)
        o = self.make_shared_pkg_data(metadata_xml=m)
        self.assertEqual(getattr(o, attr), "foon")

    for x in ("longdescription", "maintainers", "herds"):
        locals()["test_%s" % x] = post_curry(generic_metadata_xml, x)
    del x

    def test_manifest(self):
        m = repo_objs.Manifest(None)
        o = self.make_shared_pkg_data(manifest=m)
        self.assertIdentical(o.manifest, m)
