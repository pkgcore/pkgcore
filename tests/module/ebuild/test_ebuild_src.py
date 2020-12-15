import os
import textwrap
from functools import partial

import pytest
from snakeoil.currying import post_curry
from snakeoil.data_source import data_source, local_source
from snakeoil.osutils import pjoin

from pkgcore import fetch
from pkgcore.ebuild import digest, ebuild_src, repo_objs
from pkgcore.ebuild.eapi import EAPI, get_eapi
from pkgcore.package import errors
from pkgcore.test import malleable_obj

from .test_eclass_cache import FakeEclassCache


class TestBase:

    kls = ebuild_src.base

    def get_pkg(self, data=None, cpv='dev-util/diffball-0.1-r1', repo=None,
                pre_args=(), suppress_unsupported=True):
        o = self.kls(*(list(pre_args) + [repo, cpv]))
        if data is not None:
            eapi_data = data.pop('EAPI', 0)
            if eapi_data is not None:
                object.__setattr__(o, 'eapi', get_eapi(
                    str(eapi_data), suppress_unsupported=suppress_unsupported))
            object.__setattr__(o, 'data', data)
        return o

    def make_parent(self, **methods):
        class kls:
            locals().update(methods)
        return kls()

    def test_init(self):
        o = self.get_pkg({}, cpv='dev-util/diffball-0.1-r1')
        assert o.category == 'dev-util'
        assert o.package == 'diffball'
        assert o.fullver == '0.1-r1'
        assert o.PN == 'diffball'
        assert o.P == 'diffball-0.1'
        assert o.PF == 'diffball-0.1-r1'
        assert o.PR == 'r1'
        assert self.get_pkg({}, 'dev-util/diffball-0.1').PR == 'r0'

    def test_path(self):
        l = []
        path = '/random/path/to/foo-0.ebuild'
        def f(self, cpv):
            l.append(cpv)
            return path
        c = self.make_parent(_get_ebuild_path=f)
        o = self.get_pkg({}, repo=c)
        assert o.path == path
        assert l == [o]

    def test_ebuild(self):
        l = []
        def f(self, cpv):
            l.append(cpv)
            return 1
        c = self.make_parent(get_ebuild_src=f)
        o = self.get_pkg({}, repo=c)
        assert o.ebuild == 1
        assert l == [o]

    def test_fetch_metadata(self):
        def f(self, cpv, **options):
            return {'1': '2'}
        o = self.get_pkg(repo=self.make_parent(_get_metadata=f))
        assert o.data == {'1': '2'}

    def test_license(self):
        o = self.get_pkg({'LICENSE': 'GPL2 FOON'})
        assert list(o.license) == ['GPL2', 'FOON']

    def test_description(self):
        o = self.get_pkg({'DESCRIPTION': ' foon\n asdf '})
        assert o.description == 'foon\n asdf'

    def test_iuse(self):
        o = self.get_pkg({})
        assert o.iuse == frozenset()
        o = self.get_pkg({'IUSE': 'build pkg foon'})
        assert o.iuse == frozenset(['build', 'foon', 'pkg'])

    def test_iuse_stripped(self):
        o = self.get_pkg({})
        assert o.iuse_stripped == frozenset()
        o = self.get_pkg({'IUSE': 'build pkg foon'})
        assert o.iuse_stripped == frozenset(['build', 'foon', 'pkg'])
        o = self.get_pkg({'EAPI': '1', 'IUSE': '+build -pkg foon'})
        assert o.iuse_stripped == frozenset(['build', 'foon', 'pkg'])

    def test_iuse_effective(self):
        o = self.get_pkg({})
        assert o.iuse_effective == frozenset()
        o = self.get_pkg({'IUSE': 'build pkg foon'})
        assert o.iuse_effective == frozenset(['build', 'foon', 'pkg'])
        o = self.get_pkg({'EAPI': '1', 'IUSE': '+build -pkg foon'})
        assert o.iuse_effective == frozenset(['build', 'foon', 'pkg'])

    def test_properties(self):
        o = self.get_pkg({})
        assert sorted(o.properties.evaluate_depset([])) == []
        o = self.get_pkg({'PROPERTIES': ''})
        assert sorted(o.properties.evaluate_depset([])) == []
        o = self.get_pkg({'PROPERTIES': 'interactive'})
        assert sorted(o.properties.evaluate_depset([])) == ['interactive']

    def test_homepage(self):
        o = self.get_pkg({'HOMEPAGE': ' http://slashdot/ '})
        assert o.homepage == ('http://slashdot/',)
        o = self.get_pkg({'HOMEPAGE': 'http://foozball.org https://foobar.com'})
        assert o.homepage == ('http://foozball.org', 'https://foobar.com')

    def test_fullslot(self):
        o = self.get_pkg({'SLOT': '0'})
        assert o.fullslot == '0'

        # subslot support
        for eapi_str, eapi in EAPI.known_eapis.items():
            if eapi.options.sub_slotting:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '0/0'})
                assert o.fullslot == '0/0'
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/2'})
                assert o.fullslot == '1/2'
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/foo-1'})
                assert o.fullslot == '1/foo-1'
            else:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '0/0'})
                with pytest.raises(errors.MetadataException):
                    o.fullslot

        # unset SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({}).fullslot
        # empty SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({'SLOT': ''}).fullslot

    def test_slot(self):
        o = self.get_pkg({'SLOT': '0'})
        assert o.slot == '0'

        # subslot support
        for eapi_str, eapi in EAPI.known_eapis.items():
            if eapi.options.sub_slotting:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/2'})
                assert o.slot == '1'
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/foo-1'})
                assert o.slot == '1'
            else:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/2'})
                with pytest.raises(errors.MetadataException):
                    o.slot

        # unset SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({}).slot
        # empty SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({'SLOT': ''}).slot

    def test_subslot(self):
        o = self.get_pkg({'SLOT': '0'})
        assert o.subslot == '0'
        o = self.get_pkg({'SLOT': '1'})
        assert o.subslot == '1'

        # subslot support
        for eapi_str, eapi in EAPI.known_eapis.items():
            if eapi.options.sub_slotting:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/2'})
                assert o.subslot == '2'
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/foo-1'})
                assert o.subslot == 'foo-1'
            else:
                o = self.get_pkg({'EAPI': eapi_str, 'SLOT': '1/2'})
                with pytest.raises(errors.MetadataException):
                    o.subslot

        # unset SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({}).subslot
        # empty SLOT variable
        with pytest.raises(errors.MetadataException):
            self.get_pkg({'SLOT': ''}).subslot

    def test_restrict(self):
        o = self.get_pkg({'RESTRICT': 'strip fetch strip'})
        assert sorted(o.restrict) == ['fetch', 'strip', 'strip']
        o = self.get_pkg({'RESTRICT': 'x? ( foo ) !x? ( dar )'})
        assert sorted(o.restrict.evaluate_depset([])) == ['dar']
        # ensure restrict doesn't have || () in it
        with pytest.raises(errors.MetadataException):
            getattr(self.get_pkg({'RESTRICT': '|| ( foon dar )'}), 'restrict')

    def test_eapi(self):
        assert str(self.get_pkg({'EAPI': '0'}).eapi) == '0'
        assert self.get_pkg({'EAPI': '0'}).eapi.is_supported
        assert not self.get_pkg({'EAPI': '0.1'}).eapi.is_supported
        assert self.get_pkg({'EAPI': 'foon'}, suppress_unsupported=False).eapi is None
        with pytest.raises(errors.MetadataException):
            getattr(self.get_pkg({'EAPI': 0, 'DEPEND': "d/b:0"}), 'depend')
        with pytest.raises(errors.MetadataException):
            getattr(self.get_pkg({'EAPI': 0, 'RDEPEND': "d/b:0"}), 'rdepend')
        with pytest.raises(errors.MetadataException):
            getattr(self.get_pkg({'EAPI': 1, 'DEPEND': "d/b[x,y]"}), 'depend')
        with pytest.raises(errors.MetadataException):
            getattr(self.get_pkg({'EAPI': 1, 'DEPEND': "d/b::foon"}), 'depend')
        assert self.get_pkg({'EAPI': 2, 'DEPEND': 'a/b[x=]'}).depend.node_conds
        pkg = self.get_pkg({'EAPI': 1, 'DEPEND': 'a/b[x=]'})
        with pytest.raises(errors.MetadataException):
            getattr(pkg, 'depend')

    def test_get_parsed_eapi(self, tmpdir):
        # ebuild has a real path on the fs
        def _path(self, cpv, eapi_str):
            ebuild = pjoin(str(tmpdir), "temp-0.ebuild")
            with open(ebuild, 'w') as f:
                f.write(textwrap.dedent(f'''\
                    # Copyright
                    # License

                    EAPI={eapi_str}'''))
            return local_source(str(ebuild))

        # ebuild is a faked obj
        def _src(self, cpv, eapi_str):
            return data_source(f'EAPI={eapi_str}')

        for func in (_path, _src):
            # verify parsing known EAPIs
            for eapi_str in EAPI.known_eapis.keys():
                c = self.make_parent(get_ebuild_src=post_curry(func, eapi_str))
                o = self.get_pkg({'EAPI': None}, repo=c)
                assert str(o.eapi) == eapi_str
            # check explicitly unsetting EAPI equates to EAPI=0
            for eapi_str in ('', '""', "''"):
                c = self.make_parent(get_ebuild_src=post_curry(func, eapi_str))
                o = self.get_pkg({'EAPI': None}, repo=c)
                assert str(o.eapi) == '0'

    def test_keywords(self):
        assert list(self.get_pkg({'KEYWORDS': ''}).keywords) == []
        assert sorted(self.get_pkg({'KEYWORDS': 'x86 amd64'}).keywords) == sorted(['x86', 'amd64'])

    def test_sorted_keywords(self):
        assert self.get_pkg({'KEYWORDS': ''}).sorted_keywords == ()
        assert self.get_pkg({'KEYWORDS': 'amd64 x86'}).sorted_keywords == ('amd64', 'x86')
        assert self.get_pkg({'KEYWORDS': 'x86 amd64'}).sorted_keywords == ('amd64', 'x86')
        assert (
            self.get_pkg({'KEYWORDS': '~amd64 ~amd64-fbsd ~x86'}).sorted_keywords ==
            ('~amd64', '~x86', '~amd64-fbsd'))
        assert (
            self.get_pkg({'KEYWORDS': '~amd64 ~x86 ~amd64-fbsd'}).sorted_keywords ==
            ('~amd64', '~x86', '~amd64-fbsd'))

    def generic_check_depends(self, depset, attr, expected=None,
                              data_name=None, eapi='0'):
        if expected is None:
            expected = depset
        if data_name is None:
            data_name = attr.upper()
        o = self.get_pkg({data_name: depset, 'EAPI': eapi})
        assert str(getattr(o, attr)) == expected
        o = self.get_pkg({data_name: '', 'EAPI': eapi})
        assert str(getattr(o, attr)) == ''
        if expected:
            with pytest.raises(errors.MetadataException):
                getattr(self.get_pkg({data_name: '|| ( ', 'EAPI': eapi}), attr)

    for x in ('depend', 'rdepend'):
        locals()[f'test_{x}'] = post_curry(generic_check_depends,
            'dev-util/diffball || ( dev-util/foo x86? ( dev-util/bsdiff ) )',
             x)
    del x
    test_pdepend = post_curry(generic_check_depends,
        'dev-util/diffball x86? ( virtual/boo )', 'pdepend')
    # BDEPEND in EAPI 7
    test_bdepend = post_curry(generic_check_depends,
        'dev-util/diffball x86? ( virtual/boo )', 'bdepend', eapi='7')
    # BDEPEND is ignored in EAPIs <= 6
    test_bdepend = post_curry(generic_check_depends,
        'dev-util/diffball x86? ( virtual/boo )', 'bdepend', expected='', eapi='0')

    def test_fetchables(self):
        l = []
        def f(self, cpv, allow_missing=False):
            l.append(cpv)
            return allow_missing, {'monkey.tgz': {}, 'boon.tgz': {}, 'foon.tar.gz': {}}
        repo = self.make_parent(_get_digests=f)
        parent = self.make_parent(_parent_repo=repo)
        # verify it does digest lookups...
        o = self.get_pkg({'SRC_URI': 'http://foo.com/bar.tgz'}, repo=parent)
        with pytest.raises(errors.MetadataException):
            getattr(o, 'fetchables')
        assert l == [o]

        # basic tests;
        for x in range(0, 3):
            f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz',
                'EAPI': str(x)},
                 repo=parent).fetchables
            assert list(f[0].uri) == ['http://foo.com/monkey.tgz']
            assert f[0].filename == 'monkey.tgz'

        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz '
            'http://dar/boon.tgz', 'EAPI': '2'},
             repo=parent).fetchables
        assert [list(x.uri) for x in f] == [['http://foo.com/monkey.tgz'], ['http://dar/boon.tgz']]
        assert [x.filename for x in f] == ['monkey.tgz', 'boon.tgz']

        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz -> foon.tar.gz',
            'EAPI': '2'},
             repo=parent).fetchables
        assert list(f[0].uri) == ['http://foo.com/monkey.tgz']
        assert f[0].filename == 'foon.tar.gz'

        o = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz -> ',
            'EAPI': '2'}, repo=parent)
        with pytest.raises(errors.MetadataException):
            getattr(o, 'fetchables')

        # verify it collapses multiple basenames down to the same.
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz '
            'http://foo.com2/monkey.tgz'}, repo=parent).fetchables
        assert list(f[0].uri) == ['http://foo.com/monkey.tgz', 'http://foo.com2/monkey.tgz']

        mirror = fetch.mirror(['http://boon.com/'], 'mirror1')
        parent = self.make_parent(_parent_repo=repo, mirrors={'mirror1': mirror})

        f = self.get_pkg(
            {'SRC_URI': 'mirror://mirror1/foon/monkey.tgz'}, repo=parent).fetchables
        assert list(f[0].uri) == ['http://boon.com/foon/monkey.tgz']

        # unknown mirrors get ignored (and flagged by pkgcheck)
        pkg = self.get_pkg({'SRC_URI': 'mirror://mirror2/foon/monkey.tgz'}, repo=parent)
        assert pkg.fetchables

        assert (
            [list(x.uri) for x in self.get_pkg(
                {'EAPI': '2', 'SRC_URI': 'mirror://mirror1/monkey.tgz -> foon.tar.gz'},
                repo=parent).fetchables] ==
            [['http://boon.com/monkey.tgz']])

        parent = self.make_parent(_parent_repo=repo,
            mirrors={'mirror1': mirror}, default_mirrors=fetch.default_mirror(
                ['http://default.com/dist/', 'http://default2.com/'],
                'default'))

        assert (
            [list(x.uri) for x in self.get_pkg(
                {'EAPI': '2', 'SRC_URI': 'mirror://mirror1/monkey.tgz -> foon.tar.gz'},
                repo=parent).fetchables] ==
            [[
                'http://default.com/dist/foon.tar.gz',
                'http://default2.com/foon.tar.gz',
                'http://boon.com/monkey.tgz']])

        parent = self.make_parent(_parent_repo=repo, default_mirrors=mirror)
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz'},
            repo=parent).fetchables
        assert list(f[0].uri) == ['http://boon.com/monkey.tgz', 'http://foo.com/monkey.tgz']

        # skip default mirrors
        pkg = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz'}, repo=parent)
        f = pkg.generate_fetchables(skip_default_mirrors=True)
        assert list(f[0].uri) == ['http://foo.com/monkey.tgz']

        # test primaryuri...
        mirror2 = fetch.mirror(['http://boon2.com/'], 'default')
        parent = self.make_parent(_parent_repo=repo, default_mirrors=mirror,
            mirrors={'mirror1': mirror2})
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz '
            'mirror://mirror1/boon.tgz', 'RESTRICT': 'primaryuri'},
            repo=parent).fetchables
        assert list(f[0].uri) == ['http://foo.com/monkey.tgz', 'http://boon.com/monkey.tgz']
        assert list(f[1].uri) == ['http://boon2.com/boon.tgz', 'http://boon.com/boon.tgz']
        assert len(f) == 2

        # restrict=mirror..
        f = self.get_pkg({'SRC_URI': 'http://foo.com/monkey.tgz',
            'RESTRICT': 'mirror'}, repo=parent).fetchables
        assert list(f[0].uri) == ['http://foo.com/monkey.tgz']
        assert len(f) == 1

        # test uri for when there *is* no uri
        f = self.get_pkg({'SRC_URI': 'monkey.tgz'}, repo=parent).fetchables
        assert list(f[0].uri) == []

    def test_required_use(self):
        for eapi_str, eapi in EAPI.known_eapis.items():
            # Check all EAPIs for REQUIRED_USE parsing, EAPIs that don't support it
            # should return depsets that evaluate to False.
            pkg = self.get_pkg({'EAPI': eapi_str, 'REQUIRED_USE': 'test? ( foo )'})
            assert bool(pkg.required_use) == eapi.options.has_required_use, \
                f"failure parsing REQUIRED_USE for EAPI '{eapi}'"

            # Render various REQUIRED_USE deps with set USE flag states and
            # check for satisfiability.
            if eapi.options.has_required_use:
                required_use_data = (
                    ('foo', '', 'foo', True),
                    ('foo', '', '', False),
                    ('!foo', 'foo', '', True),
                    ('!foo', 'foo', 'foo', False),
                    ('foo bar', '', 'foo bar', True),
                    ('foo bar', '', 'bar foo', True),
                    ('( foo bar )', '', 'foo', False),
                    ('( foo bar )', '', 'foo bar', True),
                    ('test? ( foo )', 'test', 'foo', True),
                    ('test? ( foo )', 'test', '', False),
                    ('test? ( !foo )', 'test', 'foo', False),
                    ('test? ( !foo )', 'test', '', True),
                    ('test? ( foo bar )', 'test', 'foo bar', True),
                    ('!test? ( foo )', 'test', '', True),
                    ('!test? ( foo )', '', 'foo', True),
                    ('|| ( test foo )', 'test', 'test', True),
                    ('|| ( test foo )', 'test', 'test foo', True),
                    ('|| ( test foo ) bar? ( foo )', 'test', 'test', True),
                    ('|| ( test foo ) bar? ( foo )', 'bar', 'foo', True),
                    ('^^ ( bar foo )', '', 'bar', True),
                    ('^^ ( bar foo )', '', 'foo', True),
                    ('^^ ( bar foo )', '', '', False),
                )

                if eapi.options.required_use_one_of:
                    required_use_data += (
                        ('?? ( bar foo )', '', 'bar', True),
                        ('?? ( bar foo )', '', 'foo', True),
                        ('?? ( bar foo )', '', '', True),
                    )
                else:
                    # EAPIs that don't support the ?? operator raise metadata exceptions if used.
                    pkg = self.get_pkg({'EAPI': eapi_str, 'REQUIRED_USE': '?? ( bar foo )'})
                    with pytest.raises(errors.MetadataException) as cm:
                        getattr(pkg, 'required_use')
                    assert f"EAPI '{eapi_str}' doesn't support '??' operator" in cm.value.error

                for required_use, iuse, use, satisfied in required_use_data:
                    pkg = self.get_pkg({'EAPI': eapi_str, 'REQUIRED_USE': required_use})
                    required_use_deps = pkg.required_use.evaluate_depset(iuse.split())
                    for node in required_use_deps:
                        assert node.match(use.split()) is satisfied, \
                            f'REQUIRED_USE="{required_use}", IUSE="{iuse}", ' \
                            f'USE="{use}", satisfied="{satisfied}"'

    def test_live(self):
        o = self.get_pkg({})
        assert not o.live
        o = self.get_pkg({'PROPERTIES': 'live'})
        assert o.live


class TestPackage(TestBase):

    kls = ebuild_src.package

    def get_pkg(self, *args, **kwds):
        kwds.setdefault("pre_args", (None,))
        return super().get_pkg(*args, **kwds)

    def test_init(self):
        super().test_init()
        o = self.get_pkg(pre_args=(1,))
        assert o._shared_pkg_data == 1

    def test_mtime_(self):
        l = []
        def f(self, cpv):
            l.append(cpv)
            return 100

        parent = self.make_parent(_get_ebuild_mtime=f)
        o = self.get_pkg(repo=parent)
        assert o._mtime_ == 100
        assert l == [o]

    def make_shared_pkg_data(self, manifest=None, metadata_xml=None):
        return self.get_pkg(
            pre_args=(repo_objs.SharedPkgData(metadata_xml, manifest),))

    def generic_metadata_xml(self, attr):
        m = repo_objs.MetadataXml(None)
        object.__setattr__(m, "_"+attr, "foon")
        object.__setattr__(m, "_source", None)
        o = self.make_shared_pkg_data(metadata_xml=m)
        assert getattr(o, attr) == "foon"

    for x in ("longdescription", "maintainers"):
        locals()[f"test_{x}"] = post_curry(generic_metadata_xml, x)
    del x

    def test_manifest(self):
        m = digest.Manifest(None)
        o = self.make_shared_pkg_data(manifest=m)
        assert o.manifest is m


class TestPackageFactory:

    kls = ebuild_src.package_factory

    def mkinst(self, repo=None, cache=(), eclasses=None, mirrors={},
               default_mirrors={}, **overrides):
        o = self.kls(repo, cache, eclasses, mirrors, default_mirrors)
        for k, v in overrides.items():
            object.__setattr__(o, k, v)
        return o

    def test_mirrors(self):
        mirrors_d = {'gentoo': ['http://bar/', 'http://far/']}
        mirrors = {k: fetch.mirror(v, k) for k, v in mirrors_d.items()}
        pf = self.mkinst(mirrors=mirrors_d)
        assert len(pf._cache) == 0
        assert sorted(pf.mirrors) == sorted(mirrors)
        assert pf.mirrors['gentoo'] == mirrors['gentoo']
        assert pf.default_mirrors == None

        def_mirrors = ['http://def1/', 'http://blah1/']
        pf = self.mkinst(default_mirrors=def_mirrors)
        assert pf.mirrors == {}
        assert list(pf.default_mirrors) == def_mirrors

    def test_get_ebuild_src(self):
        assert (
            self.mkinst(
                repo=malleable_obj(_get_ebuild_src=lambda s: f"lincoln haunts me: {s}")
                ).get_ebuild_src("1") ==
            "lincoln haunts me: 1")

    def test_get_ebuild_mtime(self, tmpdir):
        f = pjoin(str(tmpdir), "temp-0.ebuild")
        open(f, 'w').close()
        mtime = self.mkinst(
            repo=malleable_obj(_get_ebuild_path=lambda s: f))._get_ebuild_mtime(None)
        assert mtime == os.stat(f).st_mtime

    def test_get_metadata(self):
        ec = FakeEclassCache('/nonexistent/path')
        pkg = malleable_obj(_mtime_=100, cpvstr='dev-util/diffball-0.71', path='bollocks')

        class fake_cache(dict):
            readonly = False
            validate_result = False
            def validate_entry(self, *args):
                return self.validate_result

        cache1 = fake_cache({pkg.cpvstr: {'_mtime_': 100, 'marker': 1}})
        cache2 = fake_cache({})

        class explode_kls(AssertionError): pass

        def explode(name, *args, **kwargs):
            raise explode_kls(
                f"{name} was called with {args!r} and {kwargs!r}, shouldn't be invoked.")

        pf = self.mkinst(
            cache=(cache2, cache1), eclasses=ec,
            _update_metadata=partial(explode, '_update_metadata'))

        cache1.validate_result = True
        assert pf._get_metadata(pkg) == {'marker': 1, '_mtime_': 100}

        assert list(cache1.keys()) == [pkg.cpvstr]
        assert not cache2

        # mtime was wiped, thus no longer is usable.
        # note also, that the caches are writable.
        cache1.validate_result = False
        with pytest.raises(explode_kls):
            pf._get_metadata(pkg)
        assert not cache2
        assert not cache1

        # Note that this is known crap eclass data; partially lazyness, partially
        # to validate the eclass validation is left to ec cache only.
        cache2.update({pkg.cpvstr:
            {'_mtime_': 200, '_eclasses_': {'eclass1': (None, 100)}, 'marker': 2}
        })
        cache2.readonly = True
        with pytest.raises(explode_kls):
            pf._get_metadata(pkg)
        assert list(cache2.keys()) == [pkg.cpvstr]
        # keep in mind the backend assumes it gets its own copy of the data.
        # thus, modifying (popping _mtime_) _is_ valid
        assert cache2[pkg.cpvstr] == \
            {'_eclasses_': {'eclass1': (None, 100)}, 'marker': 2, '_mtime_': 200}
