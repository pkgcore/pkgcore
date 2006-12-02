# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
from pkgcore.test import TestCase
from pkgcore.test.mixins import TempDirMixin
from pkgcore.ebuild import profiles
from pkgcore.util.osutils import join as pjoin
from pkgcore.util.currying import pre_curry
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
        self.assertEqual(ProfileNode(path).masks, empty);
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
        
