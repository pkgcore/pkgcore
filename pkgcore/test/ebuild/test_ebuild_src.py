# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os

from pkgcore.test import TestCase
from snakeoil.test.mixins import tempdir_decorator
from snakeoil.osutils import pjoin
from snakeoil.currying import post_curry, partial

from pkgcore import fetch
from pkgcore.package import errors
from pkgcore.test import malleable_obj
from pkgcore.test.ebuild.test_eclass_cache import FakeEclassCache
from pkgcore.ebuild import ebuild_src, digest, repo_objs, const, errors as ebuild_errors


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
        o = self.get_pkg({'RESTRICT': 'strip fetch strip'})
        self.assertEqual(*map(sorted, (o.restrict, ['strip', 'fetch', 'strip'])))
        # regression test to ensure it onnly grabs 'no' prefix, instead of lstriping it
        self.assertEqual(list(self.get_pkg({'RESTRICT': 'onoasdf'}).restrict),
            ['onoasdf'])
        self.assertEqual(sorted(self.get_pkg({'RESTRICT':'nofetch'}).restrict),
            ['fetch'])
        o = self.get_pkg({'RESTRICT': 'x? ( foo ) !x? ( dar )'})
        self.assertEqual(sorted(o.restrict.evaluate_depset([])),
            ['dar'])
        # ensure restrict doesn't have || () in it
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({'RESTRICT':'|| ( foon dar )'}), 'restrict')

    def test_eapi(self):
        self.assertEqual(self.get_pkg({'EAPI': '0'}).eapi, 0)
        self.assertEqual(self.get_pkg({'EAPI': ''}).eapi, 0)
        self.assertEqual(self.get_pkg({'EAPI': 'foon'}).eapi,
            "unsupported")
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({'EAPI':0, 'DEPEND':"d/b:0"}), 'depends')
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({'EAPI':0, 'RDEPEND':"d/b:0"}), 'rdepends')
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({'EAPI':1, 'DEPEND':"d/b[x,y]"}), 'depends')
        self.assertRaises(errors.MetadataException, getattr,
            self.get_pkg({'EAPI':1, 'DEPEND':"d/b::foon"}), 'depends')
        self.get_pkg({'EAPI':1, 'DEPEND':'d/b:foon'}).slot
        self.assertTrue(self.get_pkg({'EAPI':2, 'DEPEND':'a/b[x=]'})
            .depends.node_conds)
        pkg = self.get_pkg({'EAPI':1, 'DEPEND':'a/b[x=]'})
        self.assertRaises(errors.MetadataException, getattr,
            pkg, 'depends')

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
        def f(self, cpv, allow_missing=False):
            l.append(cpv)
            return {'monkey.tgz': {}, 'boon.tgz': {}, 'foon.tar.gz': {}}
        repo = self.make_parent(_get_digests=f)
        parent = self.make_parent(_parent_repo=repo)
        # verify it does digest lookups...
        o = self.get_pkg({'SRC_URI':'http://foo.com/bar.tgz'}, repo=parent)
        self.assertRaises(errors.MetadataException, getattr, o, 'fetchables')
        self.assertEqual(l, [o])

        # basic tests;
        for x in xrange(0,3):
            f = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz',
                'EAPI':str(x)},
                 repo=parent).fetchables
            self.assertEqual(list(f[0].uri), ['http://foo.com/monkey.tgz'])
            self.assertEqual(f[0].filename, 'monkey.tgz')

        f = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz '
            'http://dar/boon.tgz', 'EAPI':'2'},
             repo=parent).fetchables
        self.assertEqual([list(x.uri) for x in f],
            [['http://foo.com/monkey.tgz'], ['http://dar/boon.tgz']])
        self.assertEqual([x.filename for x in f],
            ['monkey.tgz', 'boon.tgz'])

        f = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz -> foon.tar.gz',
            'EAPI':'2'},
             repo=parent).fetchables
        self.assertEqual(list(f[0].uri), ['http://foo.com/monkey.tgz'])
        self.assertEqual(f[0].filename, 'foon.tar.gz')

        o = self.get_pkg({'SRC_URI':'http://foo.com/monkey.tgz -> ',
            'EAPI':'2'}, repo=parent)
        self.assertRaises(errors.MetadataException, getattr, o, 'fetchables')

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

        self.assertEqual([list(x.uri) for x in self.get_pkg({'EAPI':'2',
            'SRC_URI': 'mirror://mirror1/monkey.tgz -> foon.tar.gz'},
            repo=parent).fetchables],
            [['http://boon.com/monkey.tgz']])

        parent = self.make_parent(_parent_repo=repo,
            mirrors={'mirror1':mirror}, default_mirrors=fetch.default_mirror(
                ['http://default.com/dist/', 'http://default2.com/'],
                'default'))

        self.assertEqual([list(x.uri) for x in self.get_pkg({'EAPI':'2',
            'SRC_URI': 'mirror://mirror1/monkey.tgz -> foon.tar.gz'},
            repo=parent).fetchables],
            [['http://default.com/dist/foon.tar.gz',
            'http://default2.com/foon.tar.gz',
            'http://boon.com/monkey.tgz']])

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
        m = digest.Manifest(None)
        o = self.make_shared_pkg_data(manifest=m)
        self.assertIdentical(o.manifest, m)


class test_package_factory(TestCase):

    kls = ebuild_src.package_factory

    def mkinst(self, repo=None, cache=(), eclasses=None, mirrors={},
        default_mirrors={}, **overrides):
        o = self.kls(repo, cache, eclasses, mirrors, default_mirrors)
        for k, v in overrides.iteritems():
            object.__setattr__(o, k, v)
        return o

    def test_mirrors(self):
        mirrors_d = {'gentoo':['http://bar/', 'http://far/']}
        mirrors = dict((k, fetch.mirror(v,k)) for k,v in mirrors_d.iteritems())
        pf = self.mkinst(mirrors=mirrors_d)
        self.assertLen(pf._cache, 0)
        self.assertEqual(sorted(pf.mirrors), sorted(mirrors))
        self.assertEqual(pf.mirrors['gentoo'], mirrors['gentoo'])
        self.assertEqual(pf.default_mirrors, None)

        def_mirrors = ['http://def1/', 'http://blah1/']
        pf = self.mkinst(default_mirrors=def_mirrors)
        self.assertEqual(pf.mirrors, {})
        self.assertEqual(list(pf.default_mirrors), def_mirrors)

    def test_get_ebuild_src(self):
        self.assertEqual(self.mkinst(repo=malleable_obj(
            _get_ebuild_src=lambda s:"lincoln haunts me: %s" % s)
            ).get_ebuild_src("1"),  "lincoln haunts me: 1")

    @tempdir_decorator
    def test_get_ebuild_mtime(self):
        f = pjoin(self.dir, "temp-0.ebuild")
        open(f, 'w')
        cur = os.stat_float_times()
        try:
            for x in (False, True):
                os.stat_float_times(x)
                self.assertEqual(self.mkinst(repo=malleable_obj(
                    _get_ebuild_path=lambda s:f))._get_ebuild_mtime(None),
                    os.stat(f).st_mtime)
        finally:
            os.stat_float_times(cur)

    def test_get_metadata(self):
        ec = FakeEclassCache('/nonexistant/path')
        pkg = malleable_obj(_mtime_=100, cpvstr='dev-util/diffball-0.71')

        class fake_cache(dict):
            readonly = False

        cache1 = fake_cache({pkg.cpvstr:
            {'_mtime_':100, '_eclasses_':{'eclass1':(None, 100)}, 'marker':1}
        })
        cache2 = fake_cache({})

        class explode_kls(AssertionError): pass

        def explode(name, *args, **kwargs):
            raise explode_kls("%s was called with %r and %r, "
                "shouldn't be invoked." % (name, args, kwargs))

        pf = self.mkinst(cache=(cache2, cache1), eclasses=ec,
            _update_metadata=partial(explode, '_update_metadata'))

        self.assertEqual(pf._get_metadata(pkg),
            {'_eclasses_':{'eclass1':(None, 100)}, 'marker':1},
            reflective=False)

        self.assertEqual(cache1.keys(), [pkg.cpvstr])
        self.assertFalse(cache2)

        # mtime was wiped, thus no longer is usable.
        # note also, that the caches are writable.
        self.assertRaises(explode_kls, pf._get_metadata, pkg)
        self.assertFalse(cache2)
        self.assertFalse(cache1)

        cache2.update({pkg.cpvstr:
            {'_mtime_':200, '_eclasses_':{'eclass1':(None, 100)}, 'marker':2}
        })
        cache2.readonly = True
        self.assertRaises(explode_kls, pf._get_metadata, pkg)
        self.assertEqual(cache2.keys(), [pkg.cpvstr])
        # keep in mind the backend assumes it gets it's own copy of the data.
        # thus, modifying (popping _mtime_) _is_ valid
        self.assertEqual(cache2[pkg.cpvstr],
            {'_eclasses_':{'eclass1':(None, 100)}, 'marker':2})

