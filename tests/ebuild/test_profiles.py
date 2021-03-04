import binascii
import errno
import os
import shutil
import tempfile
from functools import partial
from unittest import mock

from snakeoil.osutils import ensure_dirs, normpath, pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin

from pkgcore.config import central
from pkgcore.ebuild import const, profiles, repo_objs
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import CPV
from pkgcore.ebuild.misc import chunked_data
from pkgcore.restrictions import packages
from pkgcore.test import silence_logging

atrue = packages.AlwaysTrue


class ProfileNode(profiles.ProfileNode):
    # re-inherited to disable inst-caching
    pass

class profile_mixin(TempDirMixin):

    def mk_profile(self, profile_name):
        return self.mk_profiles({'name':profile_name})

    def mk_profiles(self, *profiles, **kwds):
        for x in os.listdir(self.dir):
            shutil.rmtree(pjoin(self.dir, x))
        for idx, vals in enumerate(profiles):
            name = str(vals.pop("name", idx))
            path = pjoin(self.dir, name)
            ensure_dirs(path)
            parent = vals.pop("parent", None)
            for fname, data in vals.items():
                with open(pjoin(path, fname), "w") as f:
                    f.write(data)

            if idx and not parent:
                parent = idx - 1

            if parent is not None:
                with open(pjoin(path, "parent"), "w") as f:
                    f.write(f"../{parent}")
        if kwds:
            for key, val in kwds.items():
                with open(pjoin(self.dir, key), "w") as f:
                    f.write(val)

    def assertEqualChunks(self, given_mapping, desired_mapping):
        def f(chunk):
            return chunked_data(chunk.key, tuple(sorted(chunk.neg)), tuple(sorted(chunk.pos)))
        given_mapping.optimize()
        return self._assertEqualPayload(given_mapping.render_to_dict(), desired_mapping, f, chunked_data)

    def assertEqualPayload(self, given_mapping, desired_mapping):
        def f(chunk):
            return chunked_data(chunk.restrict, tuple(sorted(chunk.data)))

        return self._assertEqualPayload(given_mapping, desired_mapping, f, chunked_data)

    assertEqualPayload = assertEqualChunks

    def _assertEqualPayload(self, given_mapping, desired_mapping, reformat_f, bare_kls):
        keys1, keys2 = set(given_mapping), set(desired_mapping)
        self.assertEqual(
            keys1, keys2,
            msg=f"keys differ: wanted {keys2!r} got {keys1!r}\nfrom {given_mapping!r}")

        for key, desired in desired_mapping.items():
            got = given_mapping[key]
            # sanity check the desired data, occasionally screw this up
            self.assertNotInstance(desired, bare_kls, msg="key %r, bad test invocation; "
                "bare %s instead of a tuple; val %r" % (key, bare_kls.__name__, got))
            self.assertInstance(got, tuple, msg="key %r, non tuple: %r" %
                (key, got))
            self.assertNotInstance(got, bare_kls, msg="key %r, bare %s, "
                "rather than tuple: %r" % (key, bare_kls.__name__, got))
            if not all(isinstance(x, bare_kls) for x in got):
                self.fail("non %s instance: key %r, val %r; types %r" % (bare_kls.__name__,
                    key, got, list(map(type, got))))
            got2, desired2 = tuple(map(reformat_f, got)), tuple(map(reformat_f, desired))
            self.assertEqual(got2, desired2, msg="key %r isn't equal; wanted %r, got %r" % (key, desired2, got2))



empty = ((), ())

class TestPmsProfileNode(profile_mixin, TestCase):

    klass = staticmethod(ProfileNode)

    def setUp(self, default=True):
        TempDirMixin.setUp(self)
        if default:
            self.profile = "default"
            self.mk_profile(self.profile)

    def wipe_path(self, path):
        try:
            os.unlink(path)
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                return
            elif e.errno != errno.EISDIR:
                raise
            shutil.rmtree(path)

    def write_file(self, filename, iterable, profile=None):
        if profile is None:
            profile = self.profile
        with open(pjoin(self.dir, profile, filename), "w") as f:
            f.write(iterable)

    def parsing_checks(self, filename, attr, data="", line_negation=True):
        path = pjoin(self.dir, self.profile)
        self.write_file(filename, data)
        getattr(self.klass(path), attr)
        self.write_file(filename,  "-")
        self.assertRaises(profiles.ProfileError,
            getattr, self.klass(path), attr)
        self.wipe_path(pjoin(path, filename))

    def simple_eapi_awareness_check(self, filename, attr,
            bad_data="dev-util/diffball\ndev-util/bsdiff:1",
            good_data="dev-util/diffball\ndev-util/bsdiff"):
        path = pjoin(self.dir, self.profile)
        # validate unset eapi=0 prior
        self.parsing_checks(filename, attr, data=good_data)
        self.write_file("eapi", "1")
        self.parsing_checks(filename, attr, data=good_data)
        self.parsing_checks(filename, attr, data=bad_data)
        self.write_file("eapi", "0")
        self.assertRaises(profiles.ProfileError,
            self.parsing_checks, filename, attr, data=bad_data)
        self.wipe_path(pjoin(path, "eapi"))

    def test_eapi(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(str(self.klass(path).eapi), '0')
        self.write_file("eapi", "1")
        self.assertEqual(str(self.klass(path).eapi), '1')
        self.write_file("eapi", "some-random-eapi-adsfafa")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'eapi')
        self.wipe_path(pjoin(path, "eapi"))

    def test_packages(self):
        p = self.klass(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, empty)
        self.parsing_checks("packages", "system")
        self.write_file("packages", "#foo\n")
        p = self.klass(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, empty)
        self.write_file("packages", "#foo\ndev-util/diffball\n")
        p = self.klass(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, empty)

        self.write_file("packages", "-dev-util/diffball\ndev-foo/bar\n*dev-sys/atom\n"
            "-*dev-sys/atom2\nlock-foo/dar")
        p = self.klass(pjoin(self.dir, self.profile))
        self.assertEqual(p.system, ((atom("dev-sys/atom2"),), (atom("dev-sys/atom"),)))
        self.simple_eapi_awareness_check('packages', 'system')

    def test_deprecated(self):
        self.assertEqual(self.klass(pjoin(self.dir, self.profile)).deprecated,
            None)
        self.write_file("deprecated", "")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(pjoin(self.dir, self.profile)), "deprecated")
        self.write_file("deprecated", "foon\n#dar\nfasd")
        self.assertEqual(list(self.klass(pjoin(self.dir,
            self.profile)).deprecated),
            ["foon", "dar\nfasd"])

    def test_pkg_provided(self):
        self.assertEqual(self.klass(pjoin(self.dir,
            self.profile)).pkg_provided,
            ((), ()))
        self.parsing_checks("package.provided", "pkg_provided")
        self.write_file("package.provided", "-dev-util/diffball-1.0")
        self.assertEqual(self.klass(pjoin(self.dir,
            self.profile)).pkg_provided,
                ((CPV.versioned("dev-util/diffball-1.0"),), ()))
        self.write_file("package.provided", "dev-util/diffball-1.0")
        self.assertEqual(self.klass(pjoin(self.dir,
            self.profile)).pkg_provided, ((),
                (CPV.versioned("dev-util/diffball-1.0"),)))

    def test_masks(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).masks, empty)
        self.parsing_checks("package.mask", "masks")
        self.write_file("package.mask", "dev-util/diffball")
        self.assertEqual(self.klass(path).masks, ((),
            (atom("dev-util/diffball"),)))
        self.write_file("package.mask", "-dev-util/diffball")
        self.assertEqual(self.klass(path).masks,
            ((atom("dev-util/diffball"),), ()))
        self.simple_eapi_awareness_check('package.mask', 'masks')

    def test_unmasks(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).unmasks, ((), ()))
        self.parsing_checks("package.unmask", "unmasks")
        self.write_file("package.unmask", "dev-util/diffball")
        self.assertEqual(
            self.klass(path).unmasks,
            ((), (atom("dev-util/diffball"),)))
        self.write_file("package.unmask", "-dev-util/diffball")
        self.assertEqual(
            self.klass(path).unmasks,
            ((atom("dev-util/diffball"),), ()))
        self.simple_eapi_awareness_check('package.unmask', 'unmasks')

    def test_pkg_deprecated(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).pkg_deprecated, ((), ()))
        self.parsing_checks("package.deprecated", "pkg_deprecated")
        self.write_file("package.deprecated", "dev-util/diffball")
        self.assertEqual(
            self.klass(path).pkg_deprecated,
            ((), (atom("dev-util/diffball"),)))
        self.write_file("package.deprecated", "-dev-util/diffball")
        self.assertEqual(
            self.klass(path).pkg_deprecated,
            ((atom("dev-util/diffball"),), ()))
        self.simple_eapi_awareness_check('package.deprecated', 'pkg_deprecated')

    def _check_package_use_files(self, path, filename, attr):
        self.write_file(filename, "dev-util/bar X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
           {"dev-util/bar":(chunked_data(atom("dev-util/bar"), (), ('X',)),)})
        self.write_file(filename, "-dev-util/bar X")
        self.assertRaises(profiles.ProfileError, getattr, self.klass(path),
            attr)

        # verify collapsing optimizations
        self.write_file(filename, "dev-util/foo X\ndev-util/foo X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})

        self.write_file(filename, "d-u/a X\n=d-u/a-1 X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),)})

        self.write_file(filename, "d-u/a X\n=d-u/a-1 -X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),
                chunked_data(atom("=d-u/a-1"), ('X',), ()),)})

        self.write_file(filename, "=d-u/a-1 X\nd-u/a X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),)})

        self.write_file(filename, "dev-util/bar -X\ndev-util/foo X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
           {"dev-util/bar":(chunked_data(atom("dev-util/bar"), ('X',), ()),),
           "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})

        self.wipe_path(pjoin(path, filename))

    def test_pkg_keywords(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).keywords, ())
        self.parsing_checks("package.keywords", "keywords")

        self.write_file("package.keywords", "dev-util/foo amd64")
        self.assertEqual(self.klass(path).keywords,
            ((atom("dev-util/foo"), ("amd64",)),))

        self.write_file("package.keywords", "")
        self.assertEqual(self.klass(path).keywords, ())

        self.write_file("package.keywords", ">=dev-util/foo-2 -amd64 ~amd64")
        self.assertEqual(self.klass(path).keywords,
            ((atom(">=dev-util/foo-2"), ("-amd64", "~amd64")),))

    def test_pkg_accept_keywords(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).accept_keywords, ())
        self.parsing_checks("package.accept_keywords", "accept_keywords")
        self.write_file("package.accept_keywords", "mmx")

        self.write_file("package.accept_keywords", "dev-util/foo ~amd64")
        self.assertEqual(self.klass(path).accept_keywords,
            ((atom("dev-util/foo"), ("~amd64",)),))

        self.write_file("package.accept_keywords", "")
        self.assertEqual(self.klass(path).accept_keywords, ())

        self.write_file("package.accept_keywords", "dev-util/bar **")
        self.assertEqual(self.klass(path).accept_keywords,
            ((atom("dev-util/bar"), ("**",)),))

        self.write_file("package.accept_keywords", "dev-util/baz")
        self.assertEqual(self.klass(path).accept_keywords,
            ((atom("dev-util/baz"), ()),))

    def test_masked_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqualChunks(self.klass(path).masked_use, {})
        self.parsing_checks("package.use.mask", "masked_use")
        self.wipe_path(pjoin(path, "package.use.mask"))
        self.parsing_checks("use.mask", "masked_use")
        self.write_file("use.mask", "")

        self._check_package_use_files(path, "package.use.mask", 'masked_use')

        self.write_file("package.use.mask", "dev-util/bar -X\ndev-util/foo X")

        self.write_file("use.mask", "mmx")
        self.assertEqualChunks(self.klass(path).masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue:(chunked_data(packages.AlwaysTrue, (), ("mmx",)),)
            })

        self.write_file("use.mask", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X', 'foon'), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx',)),),
            atrue:(chunked_data(packages.AlwaysTrue, ('foon',), ('mmx',)),)
            })

        # verify that use.mask is layered first, then package.use.mask
        self.write_file("package.use.mask", "dev-util/bar -mmx foon")
        self.assertEqualChunks(self.klass(path).masked_use,
            {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar":(chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),)
            })

        self.write_file("package.use.mask", "")
        self.assertEqualChunks(self.klass(path).masked_use,
           {atrue:(chunked_data(atrue, ('foon',),('mmx',)),)})
        self.simple_eapi_awareness_check('package.use.mask', 'masked_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

        self.write_file("package.use.mask", "dev-util/diffball")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'masked_use')

    def test_stable_masked_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})

        # use.stable.mask/package.use.stable.mask only >= EAPI 5
        self.write_file("use.stable.mask", "mmx")
        self.write_file("package.use.stable.mask", "dev-util/bar mmx")
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})
        self.wipe_path(pjoin(path, 'use.stable.mask'))
        self.wipe_path(pjoin(path, 'package.use.stable.mask'))

        self.simple_eapi_awareness_check('package.use.stable.mask', 'stable_masked_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

        self.write_file("eapi", "5")
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})
        self.parsing_checks("package.use.stable.mask", "stable_masked_use")
        self.wipe_path(pjoin(path, "package.use.stable.mask"))
        self.parsing_checks("use.stable.mask", "stable_masked_use")
        self.wipe_path(pjoin(path, 'use.stable.mask'))

        self._check_package_use_files(path, "package.use.stable.mask", 'stable_masked_use')

        self.write_file("package.use.stable.mask", "dev-util/bar -X\ndev-util/foo X")

        self.write_file("use.stable.mask", "mmx")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue:(chunked_data(packages.AlwaysTrue, (), ("mmx",)),)
            })

        self.write_file("use.stable.mask", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X', 'foon'), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx',)),),
            atrue:(chunked_data(packages.AlwaysTrue, ('foon',), ('mmx',)),)
            })

        # verify that use.stable.mask is layered first, then package.use.stable.mask
        self.write_file("package.use.stable.mask", "dev-util/bar -mmx foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar":(chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),)
            })

        self.write_file("package.use.stable.mask", "")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {atrue:(chunked_data(atrue, ('foon',),('mmx',)),)})

        self.write_file("package.use.stable.mask", "dev-util/diffball")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'stable_masked_use')

        # verify that settings stack in the following order:
        # use.mask -> use.stable.mask -> package.use.mask -> package.use.stable.mask
        self.write_file("use.mask", "mmx")
        self.write_file("use.stable.mask", "-foon")
        self.write_file("package.use.mask", "dev-util/foo -mmx")
        self.write_file("package.use.stable.mask", "dev-util/bar foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon', 'mmx'), ()),),
           "dev-util/bar":
               (chunked_data(atom("dev-util/bar"), (), ('foon', 'mmx')),),
           atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
           })

        self.write_file("use.mask", "-mmx")
        self.write_file("use.stable.mask", "foon")
        self.write_file("package.use.mask", "dev-util/foo mmx")
        self.write_file("package.use.stable.mask", "dev-util/foo -foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon',), ('mmx',)),),
           atrue:(chunked_data(atrue, ('mmx',), ('foon',)),)
           })

    def test_forced_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqualChunks(self.klass(path).forced_use, {})
        self.parsing_checks("package.use.force", "forced_use")
        self.wipe_path(pjoin(path, 'package.use.force'))
        self.parsing_checks("use.force", "forced_use")
        self.write_file("use.force", "")

        self._check_package_use_files(path, "package.use.force", 'forced_use')

        self.write_file("package.use.force", "dev-util/bar -X\ndev-util/foo X")

        self.write_file("use.force", "mmx")
        self.assertEqualChunks(self.klass(path).forced_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue:(chunked_data(atrue, (), ('mmx',)),),
            })

        self.write_file("use.force", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).forced_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X', 'foon',), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx')),),
            atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
            })

        # verify that use.force is layered first, then package.use.force
        self.write_file("package.use.force", "dev-util/bar -mmx foon")
        p = self.klass(path)
        self.assertEqualChunks(self.klass(path).forced_use,
            {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar":(chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),)
            })

        self.write_file("package.use.force", "")
        self.assertEqualChunks(self.klass(path).forced_use,
            {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
            })
        self.simple_eapi_awareness_check('package.use.force', 'forced_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

        self.write_file("package.use.force", "dev-util/diffball")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'forced_use')

    def test_stable_forced_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})

        # use.stable.force/package.use.stable.force only >= EAPI 5
        self.write_file("use.stable.force", "mmx")
        self.write_file("package.use.stable.force", "dev-util/bar mmx")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})
        self.wipe_path(pjoin(path, 'use.stable.force'))
        self.wipe_path(pjoin(path, 'package.use.stable.force'))

        self.simple_eapi_awareness_check('package.use.stable.force', 'stable_forced_use',
           bad_data='=de/bs-1:1 x\nda/bs y',
           good_data='=de/bs-1 x\nda/bs y')

        self.write_file("eapi", "5")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})
        self.parsing_checks("package.use.stable.force", "stable_forced_use")
        self.wipe_path(pjoin(path, 'package.use.stable.force'))
        self.parsing_checks("use.stable.force", "stable_forced_use")
        self.wipe_path(pjoin(path, 'use.stable.force'))

        self._check_package_use_files(path, "package.use.stable.force", 'stable_forced_use')

        self.write_file("package.use.stable.force", "dev-util/bar -X\ndev-util/foo X")

        self.write_file("use.stable.force", "mmx")
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {"dev-util/bar":
               (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
           "dev-util/foo":
               (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
           atrue:(chunked_data(atrue, (), ('mmx',)),),
           })

        self.write_file("use.stable.force", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {"dev-util/bar":
               (chunked_data(atom("dev-util/bar"), ('X', 'foon',), ('mmx',)),),
           "dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx')),),
           atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
           })

        # verify that use.stable.force is layered first, then package.use.stable.force
        self.write_file("package.use.stable.force", "dev-util/bar -mmx foon")
        p = self.klass(path)
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),),
           "dev-util/bar":(chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),)
           })

        self.write_file("package.use.stable.force", "")
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
           })

        self.write_file("package.use.stable.force", "dev-util/diffball")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'stable_forced_use')

        # verify that settings stack in the following order:
        # use.force -> use.stable.force -> package.use.force -> package.use.stable.force
        self.write_file("use.force", "mmx")
        self.write_file("use.stable.force", "-foon")
        self.write_file("package.use.force", "dev-util/foo -mmx")
        self.write_file("package.use.stable.force", "dev-util/bar foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon', 'mmx'), ()),),
           "dev-util/bar":
               (chunked_data(atom("dev-util/bar"), (), ('foon', 'mmx')),),
           atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
           })

        self.write_file("use.force", "-mmx")
        self.write_file("use.stable.force", "foon")
        self.write_file("package.use.force", "dev-util/foo mmx")
        self.write_file("package.use.stable.force", "dev-util/foo -foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon',), ('mmx',)),),
           atrue:(chunked_data(atrue, ('mmx',), ('foon',)),)
           })

    def test_pkg_use(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqualChunks(self.klass(path).pkg_use, {})
        self.parsing_checks("package.use", "pkg_use")
        self.write_file("package.use", "dev-util/bar X")
        self.assertEqualChunks(self.klass(path).pkg_use,
            {"dev-util/bar":(chunked_data(atom("dev-util/bar"), (), ('X',)),)})
        self.write_file("package.use", "-dev-util/bar X")
        self.assertRaises(profiles.ProfileError, getattr, self.klass(path),
            "pkg_use")

        self._check_package_use_files(path, "package.use", 'pkg_use')

        self.write_file("package.use", "dev-util/bar -X\ndev-util/foo X")
        self.assertEqualChunks(self.klass(path).pkg_use,
            {"dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X',), ()),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})
        self.simple_eapi_awareness_check('package.use', 'pkg_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

        self.write_file("package.use", "dev-util/diffball")
        self.assertRaises(profiles.ProfileError, getattr,
            self.klass(path), 'pkg_use')

    def test_parents(self):
        path = pjoin(self.dir, self.profile)
        os.mkdir(pjoin(path, 'child'))
        self.write_file("parent", "..", profile=f"{self.profile}/child")
        p = self.klass(pjoin(path, "child"))
        self.assertEqual(1, len(p.parents))
        self.assertEqual(p.parents[0].path, path)

    def test_default_env(self):
        path = pjoin(self.dir, self.profile)
        self.assertEqual(self.klass(path).default_env, {})
        self.write_file("make.defaults", "X=foo\n")
        self.assertEqual(self.klass(path).default_env, {'X':'foo'})
        self.write_file('make.defaults', 'y=narf\nx=${y}\n')
        self.assertEqual(self.klass(path).default_env,
            {'y':'narf', 'x':'narf'})
        # ensure make.defaults can access the proceeding env.
        child = pjoin(path, 'child')
        os.mkdir(child)
        self.write_file('make.defaults', 'x="${x} twice"', profile=child)
        self.write_file('parent', '..', profile=child)
        self.assertEqual(self.klass(child).default_env,
            {'y':'narf', 'x':'narf twice'})

    def test_default_env_incrementals(self):
        self.assertIn("USE", const.incrementals)
        profile1 = pjoin(self.dir, self.profile)
        profile2 = pjoin(profile1, "sub")
        profile3 = pjoin(profile2, "sub")
        os.mkdir(profile2)
        os.mkdir(profile3)
        self.write_file("make.defaults", 'USE=foo', profile=profile1)
        self.write_file("make.defaults", 'x=dar', profile=profile2)
        self.write_file("parent", "..", profile=profile2)
        self.write_file("make.defaults", 'USE=-foo', profile=profile3)
        self.write_file("parent", "..", profile=profile3)
        self.assertEqual(self.klass(profile1).default_env,
            dict(USE="foo"))
        self.assertEqual(self.klass(profile2).default_env,
            dict(USE="foo", x="dar"))
        self.assertEqual(self.klass(profile3).default_env,
            dict(USE="foo -foo", x="dar"))

    def test_bashrc(self):
        path = pjoin(self.dir, self.profile)
        self.assertIdentical(self.klass(path).bashrc, None)
        self.write_file("profile.bashrc", '')
        self.assertNotEqual(self.klass(path).bashrc, None)


class TestPortage1ProfileNode(TestPmsProfileNode):

    can_be_dirs = frozenset([
        "package.accept_keywords", "package.keywords",
        "package.mask", "package.provided", "package.unmask",
        "package.use", "package.use.force", "package.use.mask",
        "package.use.stable.force", "package.use.stable.mask",
        "use.force", "use.mask", "use.stable.mask", "use.stable.force"
    ])

    klass = partial(TestPmsProfileNode.klass, pms_strict=False)

    def write_file(self, filename, iterable, profile=None):
        if not filename in self.can_be_dirs:
            return TestPmsProfileNode.write_file(self, filename, iterable,
                profile=profile)
        if profile is None:
            profile = self.profile
        base = pjoin(self.dir, profile, filename)
        iterable = iterable.split("\n")
        if os.path.exists(base):
            self.wipe_path(base)
        os.mkdir(base)

        for idx, data in enumerate(iterable):
            with open(pjoin(base, str(idx)), 'w') as f:
                f.write(data)

    def test_skip_dotfiles(self):
        path = pjoin(self.dir, self.profile)

        self.write_file("package.keywords", "dev-util/foo amd64")
        with open(pjoin(path, "package.keywords", ".test"), 'w') as f:
            f.write('dev-util/foo x86')
        self.assertEqual(
            self.klass(path).keywords,
            ((atom("dev-util/foo"), ("amd64",)),))

        self.write_file("package.keywords", "")
        with open(pjoin(path, "package.keywords", ".test"), 'w') as f:
            f.write('dev-util/foo x86')
        self.assertEqual(self.klass(path).keywords, ())


class TestPortage2ProfileNode(TestPortage1ProfileNode):

    def setup_repo(self):
        self.repo_name = str(binascii.b2a_hex(os.urandom(10)))
        with open(pjoin(self.dir, "profiles", "repo_name"), "w") as f:
            f.write(self.repo_name)
        ensure_dirs(pjoin(self.dir, "metadata"))
        metadata = "masters = ''\nprofile-formats = portage-2"
        with open(pjoin(self.dir, "metadata", "layout.conf"), "w") as f:
            f.write(metadata)

    def setUp(self, default=True):
        TempDirMixin.setUp(self)
        if default:
            self.profile = pjoin("profiles", "default")
            self.mk_profile(self.profile)
            self.setup_repo()


class TestProfileSetProfileNode(TestPmsProfileNode):

    def setup_repo(self):
        self.repo_name = str(binascii.b2a_hex(os.urandom(10)))
        with open(pjoin(self.dir, "profiles", "repo_name"), "w") as f:
            f.write(self.repo_name)
        ensure_dirs(pjoin(self.dir, "metadata"))
        metadata = "masters = ''\nprofile-formats = profile-set"
        with open(pjoin(self.dir, "metadata", "layout.conf"), "w") as f:
            f.write(metadata)

    def setUp(self, default=True):
        TempDirMixin.setUp(self)
        if default:
            self.profile = pjoin("profiles", "default")
            self.mk_profile(self.profile)
            self.setup_repo()

    def test_packages(self):
        self.write_file("packages", "dev-sys/atom\n-dev-sys/atom2\n")
        p = self.klass(pjoin(self.dir, self.profile))
        self.assertEqual(p.profile_set, ((atom("dev-sys/atom2"),), (atom("dev-sys/atom"),)))


class TestOnDiskProfile(profile_mixin, TestCase):

    # use a derivative, using the inst caching disabled ProfileNode kls
    # from above
    class kls(profiles.OnDiskProfile):
        _node_kls = ProfileNode

    def get_profile(self, profile, basepath=None, **kwds):
        config = central.ConfigManager()
        if basepath is None:
            basepath = self.dir
        return self.kls(basepath, profile, config, **kwds)

    def test_stacking(self):
        self.mk_profiles(
            {},
            {}
        )
        base = self.get_profile("0")
        self.assertEqual([x.path for x in base.stack],
            [self.dir, pjoin(self.dir, "0")])
        self.assertEqual(len(base.system), 0)
        self.assertEqual(len(base.masks), 0)
        self.assertEqual(base.default_env, {})
        self.assertFalse(base.masked_use)
        self.assertFalse(base.forced_use)
        self.assertEqual(len(base.bashrc), 0)

    def test_packages(self):
        self.mk_profiles(
            {"packages":"*dev-util/diffball\ndev-util/foo\ndev-util/foo2\n"},
            {"packages":"*dev-util/foo\n-*dev-util/diffball\n-dev-util/foo2\n"},
            {"packages":"*dev-util/foo\n", "parent":"0"},
            {"packages":"-*\n*dev-util/foo\n", "parent":"0"},
            {"packages":"*dev-util/foo\n-*\n", "parent":"0"},
            {"packages":"-*\n", "parent":"0"},
        )
        p = self.get_profile("0")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/diffball")]))
        self.assertEqual(sorted(p.masks), [])

        p = self.get_profile("1")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/foo")]))
        self.assertEqual(sorted(p.masks), [])

        p = self.get_profile("2")
        self.assertEqual(
            sorted(p.system),
            sorted([atom("dev-util/diffball"), atom("dev-util/foo")]))

        p = self.get_profile("3")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/foo")]))

        p = self.get_profile("4")
        self.assertEqual(sorted(p.system), sorted([atom("dev-util/foo")]))

        p = self.get_profile("5")
        self.assertEqual(p.system, frozenset())

    def test_masks(self):
        self.mk_profiles(
            {"package.mask":"dev-util/foo"},
            {},
            {"package.mask":"-dev-util/confcache\ndev-util/foo"},
            **{"package.mask":"dev-util/confcache"}
        )
        self.assertEqual(
            sorted(self.get_profile("0").masks),
            sorted(atom("dev-util/" + x) for x in ["confcache", "foo"]))
        self.assertEqual(
            sorted(self.get_profile("1").masks),
            sorted(atom("dev-util/" + x) for x in ["confcache", "foo"]))
        self.assertEqual(
            sorted(self.get_profile("2").masks),
            [atom("dev-util/foo")])

    def test_unmasks(self):
        self.mk_profiles(
            {"package.unmask":"dev-util/foo"},
            {},
            {"package.unmask":"dev-util/confcache"}
        )
        self.assertEqual(
            self.get_profile("0").unmasks,
            frozenset([atom("dev-util/foo")]))
        self.assertEqual(
            self.get_profile("1").unmasks,
            frozenset([atom("dev-util/foo")]))
        self.assertEqual(
            self.get_profile("2").unmasks,
            frozenset([atom("dev-util/" + x) for x in ("confcache", "foo")]))

    def test_pkg_deprecated(self):
        self.mk_profiles(
            {"package.deprecated":"dev-util/foo"},
            {},
            {"package.deprecated":"dev-util/confcache"}
        )
        self.assertEqual(
            self.get_profile("0").pkg_deprecated,
            frozenset([atom("dev-util/foo")]))
        self.assertEqual(
            self.get_profile("1").pkg_deprecated,
            frozenset([atom("dev-util/foo")]))
        self.assertEqual(
            self.get_profile("2").pkg_deprecated,
            frozenset([atom("dev-util/" + x) for x in ("confcache", "foo")]))

    def test_bashrc(self):
        self.mk_profiles(
            {"profile.bashrc":""},
            {},
            {"profile.bashrc":""}
        )
        self.assertEqual(len(self.get_profile("0").bashrc), 1)
        self.assertEqual(len(self.get_profile("1").bashrc), 1)
        self.assertEqual(len(self.get_profile("2").bashrc), 2)

    def test_pkg_keywords(self):
        self.mk_profiles({})
        self.assertEqual(self.get_profile("0").keywords, ())

        self.mk_profiles(
            {"package.keywords": "dev-util/foo amd64"},
            {},
            {"package.keywords": ">=dev-util/foo-2 -amd64 ~amd64"}
        )
        self.assertEqual(self.get_profile("0").keywords,
            ((atom("dev-util/foo"), ("amd64",)),))
        self.assertEqual(self.get_profile("1").keywords,
            ((atom("dev-util/foo"), ("amd64",)),))
        self.assertEqual(self.get_profile("2").keywords,
            ((atom("dev-util/foo"), ("amd64",)),
            (atom(">=dev-util/foo-2"), ("-amd64", "~amd64"))))

    def test_pkg_accept_keywords(self):
        self.mk_profiles({})
        self.assertEqual(self.get_profile("0").accept_keywords, ())

        self.mk_profiles(
            {"package.accept_keywords": "dev-util/foo ~amd64"},
            {},
            {"package.accept_keywords": "dev-util/bar **"},
            {"package.accept_keywords": "dev-util/baz"}
        )
        self.assertEqual(self.get_profile("0").accept_keywords,
            ((atom("dev-util/foo"), ("~amd64",)),))
        self.assertEqual(self.get_profile("1").accept_keywords,
            ((atom("dev-util/foo"), ("~amd64",)),))
        self.assertEqual(self.get_profile("2").accept_keywords,
            ((atom("dev-util/foo"), ("~amd64",)),
            (atom("dev-util/bar"), ("**",))))
        self.assertEqual(self.get_profile("3").accept_keywords,
            ((atom("dev-util/foo"), ("~amd64",)),
            (atom("dev-util/bar"), ("**",)),
            (atom("dev-util/baz"), ())))

    def test_masked_use(self):
        self.mk_profiles({})
        self.assertEqualPayload(self.get_profile("0").masked_use, {})

        self.mk_profiles(
            {"use.mask":"X\nmmx\n"},
            {},
            {"use.mask":"-X"})

        self.assertEqualPayload(self.get_profile("0").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})

        self.assertEqualPayload(self.get_profile("1").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx',)),)})

        self.assertEqualPayload(self.get_profile("2").masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})


        self.mk_profiles(
            {"use.mask":"X\nmmx\n", "package.use.mask":"dev-util/foo cups"},
            {"package.use.mask": "dev-util/foo -cups"},
            {"use.mask":"-X", "package.use.mask": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile("0").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "cups", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile("1").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile("2").masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X', 'cups'), ("mmx",)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ("X", "mmx",)),)
            })

        self.mk_profiles(
            {"use.mask":"X", "package.use.mask":"dev-util/foo -X"},
            {"use.mask":"X"},
            {"package.use.mask":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile("0").masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('X',), ()),)
            })
        self.assertEqualPayload(self.get_profile("1").masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })
        self.assertEqualPayload(self.get_profile("2").masked_use,
            {atrue:(chunked_data(atrue, (), ("X")),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),)
            })

        # pkgcore bug 237; per PMS, later profiles can punch wholes in the
        # ranges applicable.
        self.mk_profiles(
            {"package.use.mask":"dev-util/foo X"},
            {"package.use.mask":">=dev-util/foo-1 -X"},
            {"package.use.mask":">=dev-util/foo-2 X"},
            {"package.use.mask":"dev-util/foo X", "name":"collapse_p"},
            {"package.use.mask":"dev-util/foo -X", "parent":"2", "name":"collapse_n"},
            )

        self.assertEqualPayload(self.get_profile("collapse_p").masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })

        self.assertEqualPayload(self.get_profile("collapse_n").masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),),
            })

    def test_stable_masked_use(self):
        self.mk_profiles({})
        self.assertEqualPayload(self.get_profile("0").stable_masked_use, {})

        self.mk_profiles(
            {"eapi":"5", "use.stable.mask":"X\nmmx\n"},
            {"eapi":"5"},
            {"eapi":"5", "use.stable.mask":"-X"})

        self.assertEqualPayload(self.get_profile("0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})

        self.assertEqualPayload(self.get_profile("1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx',)),)})

        self.assertEqualPayload(self.get_profile("2").stable_masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(
            {"eapi":"5", "use.stable.mask":"X\nmmx\n", "package.use.stable.mask":"dev-util/foo cups"},
            {"eapi":"5", "package.use.stable.mask": "dev-util/foo -cups"},
            {"eapi":"5", "use.stable.mask":"-X", "package.use.stable.mask": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile("0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "cups", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile("1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile("2").stable_masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X', 'cups'), ("mmx",)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ("X", "mmx",)),)
            })

        self.mk_profiles(
            {"eapi":"5", "use.stable.mask":"X", "package.use.stable.mask":"dev-util/foo -X"},
            {"eapi":"5", "use.stable.mask":"X"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile("0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('X',), ()),)
            })
        self.assertEqualPayload(self.get_profile("1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })
        self.assertEqualPayload(self.get_profile("2").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X")),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),)
            })

        # pkgcore bug 237; per PMS, later profiles can punch wholes in the
        # ranges applicable.
        self.mk_profiles(
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo X"},
            {"eapi":"5", "package.use.stable.mask":">=dev-util/foo-1 -X"},
            {"eapi":"5", "package.use.stable.mask":">=dev-util/foo-2 X"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo X", "name":"collapse_p"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo -X", "parent":"2", "name":"collapse_n"},
            )

        self.assertEqualPayload(self.get_profile("collapse_p").stable_masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })

        self.assertEqualPayload(self.get_profile("collapse_n").stable_masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),),
            })

    def test_forced_use(self):
        self.mk_profiles({})
        self.assertEqualPayload(self.get_profile("0").forced_use, {})
        self.mk_profiles(
            {"use.force":"X\nmmx\n"},
            {},
            {"use.force":"-X"})

        self.assertEqualPayload(self.get_profile("0").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile("1").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile("2").forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(
            {"use.force":"X\nmmx\n", "package.use.force":"dev-util/foo cups"},
            {"package.use.force": "dev-util/foo -cups"},
            {"use.force":"-X", "package.use.force": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile("0").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "mmx", "cups",)),),
            })
        self.assertEqualPayload(self.get_profile("1").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })
        self.assertEqualPayload(self.get_profile("2").forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups', 'X'), ('mmx',)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ('X', "mmx")),),
            })

        self.mk_profiles(
            {"use.force":"X", "package.use.force":"dev-util/foo -X"},
            {"use.force":"X"},
            {"package.use.force":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile("0").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })
        self.assertEqualPayload(self.get_profile("1").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),),
            })
        self.assertEqualPayload(self.get_profile("2").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })

    def test_stable_forced_use(self):
        self.mk_profiles({})
        self.assertEqualPayload(self.get_profile("0").stable_forced_use, {})
        self.mk_profiles(
            {"eapi":"5", "use.stable.force":"X\nmmx\n"},
            {"eapi":"5"},
            {"eapi":"5", "use.stable.force":"-X"}
        )

        self.assertEqualPayload(self.get_profile("0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile("1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile("2").stable_forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(
            {"eapi":"5", "use.stable.force":"X\nmmx\n", "package.use.stable.force":"dev-util/foo cups"},
            {"eapi":"5", "package.use.stable.force":"dev-util/foo -cups"},
            {"eapi":"5", "use.stable.force":"-X", "package.use.stable.force":"dev-util/blah X"}
        )

        self.assertEqualPayload(self.get_profile("0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "mmx", "cups",)),),
            })
        self.assertEqualPayload(self.get_profile("1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })
        self.assertEqualPayload(self.get_profile("2").stable_forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups', 'X'), ('mmx',)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ('X', "mmx")),),
            })

        self.mk_profiles(
            {"eapi":"5", "use.stable.force":"X", "package.use.stable.force":"dev-util/foo -X"},
            {"eapi":"5", "use.stable.force":"X"},
            {"eapi":"5", "package.use.stable.force":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile("0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })
        self.assertEqualPayload(self.get_profile("1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),),
            })
        self.assertEqualPayload(self.get_profile("2").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })

    def test_pkg_use(self):
        self.mk_profiles({})
        self.assertEqualPayload(self.get_profile("0").pkg_use, {})
        self.mk_profiles(
            {"package.use":"dev-util/bsdiff X mmx\n"},
            {},
            {"package.use":"dev-util/bsdiff -X\n"},
            {"package.use":"dev-util/bsdiff -mmx\ndev-util/diffball X"},
            {"package.use":"dev-util/bsdiff X\ndev-util/diffball -X\n"}
            )

        self.assertEqualPayload(self.get_profile("0").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), (), ('X', 'mmx')),)
            })
        self.assertEqualPayload(self.get_profile("1").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), (), ('X', 'mmx')),)
            })
        self.assertEqualPayload(self.get_profile("2").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('X',), ('mmx',)),)
            })
        self.assertEqualPayload(self.get_profile("3").pkg_use,
            {'dev-util/diffball':
                (chunked_data(atom("dev-util/diffball"), (), ('X',)),),
            'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('X', 'mmx'), ()),),
            })
        self.assertEqualPayload(self.get_profile("4").pkg_use,
            {'dev-util/diffball':
                (chunked_data(atom("dev-util/diffball"), ('X',), ()),),
            'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('mmx',), ('X',)),),
            })

    def test_default_env(self):
        self.assertIn('USE', const.incrementals_unfinalized)
        self.assertIn('USE', const.incrementals)
        self.assertIn('USE_EXPAND', const.incrementals)

        # first, verify it behaves correctly for unfinalized incrementals.
        self.mk_profiles({})
        self.assertEqual(self.get_profile("0").default_env, {})
        self.mk_profiles(
            {"make.defaults":"USE=y\n"},
            {},
            {"make.defaults":"USE=-y\nY=foo\n"})
        self.assertEqual(self.get_profile('0').default_env,
           {"USE":tuple('y')})
        self.assertEqual(self.get_profile('1').default_env,
           {"USE":tuple('y')})
        self.assertEqual(self.get_profile('2').default_env,
           {'Y':'foo',  "USE":('y', '-y')})

        # next, verify it optimizes for the finalized incrementals
        self.mk_profiles({})
        self.assertEqual(self.get_profile("0").default_env, {})
        self.mk_profiles(
            {"make.defaults":"USE_EXPAND=y\n"},
            {},
            {"make.defaults":"USE_EXPAND=-y\nY=foo\n"})
        self.assertEqual(self.get_profile('0').default_env,
           {"USE_EXPAND":tuple('y')})
        self.assertEqual(self.get_profile('1').default_env,
           {"USE_EXPAND":tuple('y')})
        self.assertEqual(self.get_profile('2').default_env,
           {'Y':'foo'})

    def test_iuse_effective(self):
        # TODO: add subprofiles for testing incrementals
        self.mk_profiles(
            {},
            {'eapi': '0',
             'make.defaults':
                'IUSE_IMPLICIT="abi_x86_64 foo"\n'
                'USE_EXPAND_IMPLICIT="ARCH ELIBC"\n'
                'USE_EXPAND_UNPREFIXED="ARCH"\n'
                'USE_EXPAND="ABI_X86 ELIBC"\n'
                'USE_EXPAND_VALUES_ARCH="amd64 arm"\n'
                'USE_EXPAND_VALUES_ELIBC="glibc uclibc"\n'},
            {'eapi': '5',
             'make.defaults':
                'IUSE_IMPLICIT="abi_x86_64 foo"\n'
                'USE_EXPAND_IMPLICIT="ARCH ELIBC"\n'
                'USE_EXPAND_UNPREFIXED="ARCH"\n'
                'USE_EXPAND="ABI_X86 ELIBC"\n'
                'USE_EXPAND_VALUES_ARCH="amd64 arm"\n'
                'USE_EXPAND_VALUES_ELIBC="glibc uclibc"\n'})

        # create repo dir and symlink profiles into it, necessary since the
        # repoconfig attr is used for EAPI < 5 to retrieve known arches and
        # doesn't work without a proper repo dir including a 'profiles' subdir
        repo = tempfile.mkdtemp()
        os.mkdir(pjoin(repo, 'metadata'))
        basepath = pjoin(repo, 'profiles')
        os.symlink(self.dir, basepath)

        # avoid RepoConfig warnings on initialization
        with open(pjoin(repo, 'metadata', 'layout.conf'), 'w') as f:
            f.write('repo-name = test\nmasters = gentoo\n')

        class RepoConfig(repo_objs.RepoConfig):
            # re-inherited to disable inst-caching
            pass

        # disable instance caching on RepoConfig otherwise the known arches
        # value will be cached
        with mock.patch('pkgcore.ebuild.repo_objs.RepoConfig', RepoConfig):
            self.assertEqual(
                self.get_profile('0', basepath).iuse_effective, frozenset())
            with open(pjoin(basepath, 'arch.list'), 'w') as f:
                f.write('amd64\narm\n')
            self.assertEqual(
                self.get_profile('0', basepath).iuse_effective,
                frozenset(['amd64', 'arm']))
            self.assertEqual(
                self.get_profile('1', basepath).iuse_effective,
                frozenset(['amd64', 'arm', 'elibc_glibc', 'elibc_uclibc']))
            self.assertEqual(
                self.get_profile('2', basepath).iuse_effective,
                frozenset(['abi_x86_64', 'foo', 'amd64', 'arm', 'abi_x86_64',
                           'elibc_glibc', 'elibc_uclibc']))
        shutil.rmtree(repo)

    def test_provides_repo(self):
        self.mk_profiles({})
        self.assertEqual(len(self.get_profile("0").provides_repo), 0)

        self.mk_profiles(
            {"package.provided":"dev-util/diffball-0.7.1"})
        self.assertEqual([x.cpvstr for x in
            self.get_profile("0").provides_repo],
            ["dev-util/diffball-0.7.1"])

        self.mk_profiles(
            {"package.provided":"dev-util/diffball-0.7.1"},
            {"package.provided":
                "-dev-util/diffball-0.7.1\ndev-util/bsdiff-0.4"}
        )
        self.assertEqual([x.cpvstr for x in
            sorted(self.get_profile("1").provides_repo)],
            ["dev-util/bsdiff-0.4"])

    def test_deprecated(self):
        self.mk_profiles({})
        self.assertFalse(self.get_profile("0").deprecated)
        self.mk_profiles(
            {"deprecated":"replacement\nfoon\n"},
            {}
            )
        self.assertFalse(self.get_profile("1").deprecated)
        self.mk_profiles(
            {},
            {"deprecated":"replacement\nfoon\n"}
            )
        self.assertTrue(self.get_profile("1").deprecated)

    def test_eapi(self):
        self.mk_profiles({})
        assert str(self.get_profile("0").eapi) == '0'
        self.mk_profiles({"eapi": "5\n"})
        assert str(self.get_profile("0").eapi) == '5'

    @silence_logging
    def test_from_abspath(self):
        self.mk_profiles({'name':'profiles'}, {'name':'profiles/1'})
        base = pjoin(self.dir, 'profiles')
        p = self.kls.from_abspath(pjoin(base, '1'))
        self.assertNotEqual(p, None)
        self.assertEqual(normpath(p.basepath), normpath(base))
        self.assertEqual(normpath(p.profile), normpath(pjoin(base, '1')))
