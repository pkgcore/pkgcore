# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, shutil

from snakeoil.test import TestCase
from snakeoil.osutils import pjoin, ensure_dirs

from pkgcore.test.mixins import TempDirMixin
from pkgcore.ebuild import profiles
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import CPV
from pkgcore.restrictions import packages

class ProfileNode(profiles.ProfileNode):
    # re-inherited to disable inst-caching
    pass

class profile_mixin(TempDirMixin):

    def mk_profile(self, profile_name):
        os.mkdir(pjoin(self.dir, profile_name))

    def setUp(self, default=True):
        TempDirMixin.setUp(self)
        if default:
            self.profile = "default"
            self.mk_profile(self.profile)


empty = ((), ())

class TestProfileNode(profile_mixin, TestCase):

    def write_file(self, filename, iterable, profile=None):
        if profile is None:
            profile = self.profile
        open(pjoin(self.dir, profile, filename), "w").write(iterable)

    def parsing_checks(self, filename, attr):
        path = pjoin(self.dir, self.profile)
        self.write_file(filename, "")
        getattr(ProfileNode(path), attr)
        self.write_file(filename,  "-")
        self.assertRaises(profiles.ProfileError,
            getattr, ProfileNode(path), attr)

    def test_packages(self):
        p = ProfileNode(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, empty)
        self.assertEqual(p.visibility, empty)
        self.parsing_checks("packages", "system")
        self.write_file("packages", "#foo\n")
        p = ProfileNode(pjoin(self.dir, self.profile))
        self.assertEqual(p.visibility, empty)
        self.assertEqual(p.system, empty)
        self.write_file("packages", "#foo\ndev-util/diffball\n")
        p = ProfileNode(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, empty)
        self.assertEqual(list(p.visibility), [(), (atom("dev-util/diffball",
            negate_vers=True),)])

        self.write_file("packages", "-dev-util/diffball\ndev-foo/bar\n*dev-sys/atom\n"
            "-*dev-sys/atom2\nlock-foo/dar")
        p = ProfileNode(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, ((atom("dev-sys/atom2"),), (atom("dev-sys/atom"),)))
        self.assertEqual([set(x) for x in p.visibility],
            [set([atom("dev-util/diffball", negate_vers=True)]),
            set([atom("dev-foo/bar", negate_vers=True),
                atom("lock-foo/dar", negate_vers=True)])
            ])

    def test_deprecated(self):
        self.assertEqual(ProfileNode(pjoin(self.dir, self.profile)).deprecated,
            None)
        self.write_file("deprecated", "")
        self.assertRaises(profiles.ProfileError, getattr,
            ProfileNode(pjoin(self.dir, self.profile)), "deprecated")
        self.write_file("deprecated", "foon\n#dar\nfasd")
        self.assertEqual(list(ProfileNode(pjoin(self.dir,
            self.profile)).deprecated),
            ["foon", "dar\nfasd"])

    def test_pkg_provided(self):
        self.assertEqual(ProfileNode(pjoin(self.dir,
            self.profile)).pkg_provided,
            ((), ()))
        self.parsing_checks("package.provided", "pkg_provided")
        self.write_file("package.provided", "-dev-util/diffball")
        self.assertEqual(ProfileNode(pjoin(self.dir,
            self.profile)).pkg_provided, ((CPV("dev-util/diffball"),), ()))
        self.write_file("package.provided", "dev-util/diffball")
        self.assertEqual(ProfileNode(pjoin(self.dir,
            self.profile)).pkg_provided, ((), (CPV("dev-util/diffball"),)))

    def test_masks(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(ProfileNode(path).masks, empty)
        self.parsing_checks("package.mask", "masks")
        self.write_file("package.mask", "dev-util/diffball")
        self.assertEqual(ProfileNode(path).masks, ((),
            (atom("dev-util/diffball"),)))
        self.write_file("package.mask", "-dev-util/diffball")
        self.assertEqual(ProfileNode(path).masks,
            ((atom("dev-util/diffball"),), ()))

    def test_masked_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(ProfileNode(path).masked_use, {})
        self.parsing_checks("package.use.mask", "masked_use")
        if os.path.exists(pjoin(path, "package.use.mask")):
            os.unlink(pjoin(path, "package.use.mask"))
        self.parsing_checks("use.mask", "masked_use")
        self.write_file("use.mask", "")
        self.write_file("package.use.mask", "dev-util/bar X")
        self.assertEqual(ProfileNode(path).masked_use,
           {atom("dev-util/bar"):((), ('X',))})
        self.write_file("package.use.mask", "-dev-util/bar X")
        self.assertRaises(profiles.ProfileError, getattr, ProfileNode(path),
            "masked_use")
        self.write_file("package.use.mask", "dev-util/bar -X\ndev-util/foo X")
        self.assertEqual(ProfileNode(path).masked_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',))})
        self.write_file("use.mask", "mmx")
        self.assertEqual(ProfileNode(path).masked_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',)),
           packages.AlwaysTrue:((),('mmx',))})
        self.write_file("use.mask", "mmx\n-foon")
        self.assertEqual(ProfileNode(path).masked_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',)),
           packages.AlwaysTrue:(('foon',),('mmx',))})
        self.write_file("package.use.mask", "")
        self.assertEqual(ProfileNode(path).masked_use,
           {packages.AlwaysTrue:(('foon',),('mmx',))})

    def test_forced_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(ProfileNode(path).forced_use, {})
        self.parsing_checks("package.use.force", "forced_use")
        if os.path.exists(pjoin(path, "package.use.force")):
            os.unlink(pjoin(path, "package.use.force"))
        self.parsing_checks("use.force", "forced_use")
        self.write_file("use.force", "")
        self.write_file("package.use.force", "dev-util/bar X")
        self.assertEqual(ProfileNode(path).forced_use,
           {atom("dev-util/bar"):((), ('X',))})
        self.write_file("package.use.force", "-dev-util/bar X")
        self.assertRaises(profiles.ProfileError, getattr, ProfileNode(path),
            "forced_use")
        self.write_file("package.use.force", "dev-util/bar -X\ndev-util/foo X")
        self.assertEqual(ProfileNode(path).forced_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',))})
        self.write_file("use.force", "mmx")
        self.assertEqual(ProfileNode(path).forced_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',)),
           packages.AlwaysTrue:((),('mmx',))})
        self.write_file("use.force", "mmx\n-foon")
        self.assertEqual(ProfileNode(path).forced_use,
           {atom("dev-util/bar"):(('X',), ()),
           atom("dev-util/foo"):((), ('X',)),
           packages.AlwaysTrue:(('foon',),('mmx',))})
        self.write_file("package.use.force", "")
        self.assertEqual(ProfileNode(path).forced_use,
           {packages.AlwaysTrue:(('foon',),('mmx',))})

    def test_parents(self):
        path = pjoin(self.dir, self.profile)
        os.mkdir(pjoin(path, 'child'))
        self.write_file("parent", "..", profile="%s/child" % self.profile)
        p = ProfileNode(pjoin(path, "child"))
        self.assertEqual(1, len(p.parents))
        self.assertEqual(p.parents[0].path, path)

    def test_virtuals(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(ProfileNode(path).virtuals, {})
        self.parsing_checks("virtuals", "virtuals")
        self.write_file("virtuals", "virtual/alsa media-sound/alsalib")
        self.assertEqual(ProfileNode(path).virtuals,
            {'alsa':atom("media-sound/alsalib")})

    def test_default_env(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(ProfileNode(path).default_env, {})
        self.write_file("make.defaults", "X=foo\n")
        self.assertEqual(ProfileNode(path).default_env, {'X':'foo'})
        self.write_file('make.defaults', 'y=narf\nx=${y}\n')
        self.assertEqual(ProfileNode(path).default_env,
            {'y':'narf', 'x':'narf'})

    def test_bashrc(self):
        path = pjoin(self.dir, self.profile)
        self.assertIdentical(ProfileNode(path).bashrc, None)
        self.write_file("profile.bashrc", '')
        self.assertNotEqual(ProfileNode(path).bashrc, None)


class test_incremental_expansion(TestCase):

    def test_it(self):
        s = set(["a", "b"])
        profiles.incremental_expansion(s, ("-a", "b", "-b", "c"))
        self.assertEqual(sorted(s), ["c"])
        self.assertRaises(ValueError,
            profiles.incremental_expansion, set(), '-')


class TestOnDiskProfile(TempDirMixin, TestCase):

    def mk_profiles(self, *profiles, **kwds):
        for x in os.listdir(self.dir):
            shutil.rmtree(pjoin(self.dir, x))
        for idx, vals in enumerate(profiles):
            path = pjoin(self.dir, "base%i" % idx)
            ensure_dirs(path)
            for fname, data in vals.iteritems():
                open(pjoin(path, fname), "w").write(data)
            if idx:
                open(pjoin(path, "parent"), "w").write("../base%i" % (idx -1))
        if kwds:
            for key, val in kwds.iteritems():
                open(pjoin(self.dir, key), "w").write(val)

    def get_profile(self, profile, **kwds):
        return profiles.OnDiskProfile(self.dir, profile, **kwds)

    def test_stacking(self):
        self.mk_profiles(
            {},
            {}
        )
        base = self.get_profile("base0")
        self.assertEqual([x.path for x in base.stack],
            [self.dir, pjoin(self.dir, "base0")])
        self.assertEqual(len(base.system), 0)
        self.assertEqual(len(base.masks), 0)
        self.assertEqual(base.virtuals, {})
        self.assertEqual(base.default_env, {})
        self.assertEqual(len(base.masked_use), 0)
        self.assertEqual(len(base.forced_use), 0)
        self.assertEqual(len(base.bashrc), 0)

    def test_packages(self):
        self.mk_profiles(
            {"packages":"*dev-util/diffball\ndev-util/foo\ndev-util/foo2\n"},
            {"packages":"*dev-util/foo\n-*dev-util/diffball\n-dev-util/foo2\n"}
        )
        p = self.get_profile("base0")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/diffball")]))
        self.assertEqual(sorted(p.masks),
            sorted(atom("dev-util/foo%s" % x, negate_vers=True) for x in ['', '2']))

        p = self.get_profile("base1")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/foo")]))
        self.assertEqual(sorted(p.masks),
            [atom("dev-util/foo", negate_vers=True)])

    def test_masks(self):
        self.mk_profiles(
            {"package.mask":"dev-util/foo"},
            {},
            {"package.mask":"-dev-util/confcache\ndev-util/foo"},
            **{"package.mask":"dev-util/confcache"}
        )
        self.assertEqual(sorted(self.get_profile("base0").masks),
            sorted(atom("dev-util/" + x) for x in ["confcache", "foo"]))
        self.assertEqual(sorted(self.get_profile("base1").masks),
            sorted(atom("dev-util/" + x) for x in ["confcache", "foo"]))
        self.assertEqual(sorted(self.get_profile("base2").masks),
            [atom("dev-util/foo")])

    def test_bashrc(self):
        self.mk_profiles(
            {"profile.bashrc":""},
            {},
            {"profile.bashrc":""}
        )
        self.assertEqual(len(self.get_profile("base0").bashrc), 1)
        self.assertEqual(len(self.get_profile("base1").bashrc), 1)
        self.assertEqual(len(self.get_profile("base2").bashrc), 2)

    def test_virtuals(self):
        self.mk_profiles(
            {"virtuals":"virtual/alsa\tdev-util/foo1\nvirtual/blah\tdev-util/blah"},
            {},
            {"virtuals":"virtual/alsa\tdev-util/foo2\nvirtual/dar\tdev-util/foo2"}
        )
        self.assertEqual(sorted(self.get_profile("base0").virtuals.iteritems()),
            sorted([("alsa", atom("dev-util/foo1")), ("blah", atom("dev-util/blah"))]))
        self.assertEqual(sorted(self.get_profile("base1").virtuals.iteritems()),
            sorted([("alsa", atom("dev-util/foo1")), ("blah", atom("dev-util/blah"))]))
        self.assertEqual(sorted(self.get_profile("base2").virtuals.iteritems()),
            sorted([("alsa", atom("dev-util/foo2")), ("blah", atom("dev-util/blah")),
                ("dar", atom("dev-util/foo2"))]))

    def test_masked_use(self):
        self.mk_profiles({})
        self.assertEqual(self.get_profile("base0").masked_use, {})
        self.mk_profiles(
            {"use.mask":"X\nmmx\n"},
            {},
            {"use.mask":"-X"})

        f = lambda d: set((k, tuple(v)) for k, v in d.iteritems())
        self.assertEqual(f(self.get_profile("base0").masked_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base1").masked_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base2").masked_use),
            f({packages.AlwaysTrue:['mmx']}))

        self.mk_profiles(
            {"use.mask":"X\nmmx\n", "package.use.mask":"dev-util/foo cups"},
            {"package.use.mask": "dev-util/foo -cups"},
            {"use.mask":"-X", "package.use.mask": "dev-util/blah X"})

        self.assertEqual(f(self.get_profile("base0").masked_use),
            f({packages.AlwaysTrue:('X', 'mmx'),
            atom("dev-util/foo"):["cups"]}))
        self.assertEqual(f(self.get_profile("base1").masked_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base2").masked_use),
            f({packages.AlwaysTrue:['mmx'],
            atom("dev-util/blah"):['X']}))

        self.mk_profiles(
            {"use.mask":"X", "package.use.mask":"dev-util/foo -X"},
            {"use.mask":"X"},
            {"package.use.mask":"dev-util/foo -X"})

        self.assertEqual(f(self.get_profile("base0").masked_use),
            f({packages.AlwaysTrue:["X"],
            atom("dev-util/foo"):["-X"]}))
        self.assertEqual(f(self.get_profile("base1").masked_use),
            f({packages.AlwaysTrue:["X"]}))
        self.assertEqual(f(self.get_profile("base2").masked_use),
            f({packages.AlwaysTrue:["X"],
            atom("dev-util/foo"):["-X"]}))


    def test_forced_use(self):
        self.mk_profiles({})
        self.assertEqual(self.get_profile("base0").forced_use, {})
        self.mk_profiles(
            {"use.force":"X\nmmx\n"},
            {},
            {"use.force":"-X"})

        f = lambda d: set((k, tuple(v)) for k, v in d.iteritems())
        self.assertEqual(f(self.get_profile("base0").forced_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base1").forced_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base2").forced_use),
            f({packages.AlwaysTrue:['mmx']}))

        self.mk_profiles(
            {"use.force":"X\nmmx\n", "package.use.force":"dev-util/foo cups"},
            {"package.use.force": "dev-util/foo -cups"},
            {"use.force":"-X", "package.use.force": "dev-util/blah X"})

        self.assertEqual(f(self.get_profile("base0").forced_use),
            f({packages.AlwaysTrue:('X', 'mmx'),
            atom("dev-util/foo"):["cups"]}))
        self.assertEqual(f(self.get_profile("base1").forced_use),
            f({packages.AlwaysTrue:('X', 'mmx')}))
        self.assertEqual(f(self.get_profile("base2").forced_use),
            f({packages.AlwaysTrue:['mmx'],
            atom("dev-util/blah"):['X']}))

        self.mk_profiles(
            {"use.force":"X", "package.use.force":"dev-util/foo -X"},
            {"use.force":"X"},
            {"package.use.force":"dev-util/foo -X"})

        self.assertEqual(f(self.get_profile("base0").forced_use),
            f({packages.AlwaysTrue:["X"],
            atom("dev-util/foo"):["-X"]}))
        self.assertEqual(f(self.get_profile("base1").forced_use),
            f({packages.AlwaysTrue:["X"]}))
        self.assertEqual(f(self.get_profile("base2").forced_use),
            f({packages.AlwaysTrue:["X"],
            atom("dev-util/foo"):["-X"]}))

    def test_default_env(self):
        self.mk_profiles({})
        self.assertEqual(self.get_profile("base0").default_env, {})
        self.mk_profiles(
            {"make.defaults":"X=y\n"},
            {},
            {"make.defaults":"X=-y\nY=foo\n"})
        self.assertEqual(self.get_profile('base0',
            incrementals=['X']).default_env,
           {'X':set('y')})
        self.assertEqual(self.get_profile('base1',
            incrementals=['X']).default_env,
           {'X':set('y')})
        self.assertEqual(self.get_profile('base2',
            incrementals=['X']).default_env,
           {'Y':'foo'})

    def test_provides_repo(self):
        self.mk_profiles({})
        self.assertEqual(len(self.get_profile("base0").provides_repo), 0)

        self.mk_profiles(
            {"package.provided":"dev-util/diffball-0.7.1"})
        self.assertEqual([x.cpvstr for x in
            self.get_profile("base0").provides_repo],
            ["dev-util/diffball-0.7.1"])

        self.mk_profiles(
            {"package.provided":"dev-util/diffball-0.7.1"},
            {"package.provided":
                "-dev-util/diffball-0.7.1\ndev-util/bsdiff-0.4"}
        )
        self.assertEqual([x.cpvstr for x in
            sorted(self.get_profile("base1").provides_repo)],
            ["dev-util/bsdiff-0.4"])

    def test_deprecated(self):
        self.mk_profiles({})
        self.assertFalse(self.get_profile("base0").deprecated)
        self.mk_profiles(
            {"deprecated":"replacement\nfoon\n"},
            {}
            )
        self.assertFalse(self.get_profile("base1").deprecated)
        self.mk_profiles(
            {},
            {"deprecated":"replacement\nfoon\n"}
            )
        self.assertTrue(self.get_profile("base1").deprecated)
