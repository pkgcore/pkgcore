import binascii
import os
import shutil
from functools import partial
from unittest import mock

import pytest
from pkgcore.config import central
from pkgcore.ebuild import const, profiles, repo_objs
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.cpv import CPV
from pkgcore.ebuild.misc import chunked_data
from pkgcore.restrictions import packages
from snakeoil.osutils import normpath

atrue = packages.AlwaysTrue


class ProfileNode(profiles.ProfileNode):
    # re-inherited to disable inst-caching
    pass


class profile_mixin:

    def mk_profile(self, tmp_path, profile_name):
        return self.mk_profiles(tmp_path, {'name': profile_name})

    def mk_profiles(self, tmp_path, *profiles, **kwds):
        for x in tmp_path.iterdir():
            shutil.rmtree(x)
        for idx, vals in enumerate(profiles):
            name = str(vals.pop("name", idx))
            path = tmp_path / name
            path.mkdir(parents=True, exist_ok=True)
            parent = vals.pop("parent", None)
            for fname, data in vals.items():
                (path / fname).write_text(data)

            if idx and not parent:
                parent = idx - 1

            if parent is not None:
                (path / "parent").write_text(f"../{parent}")
        if kwds:
            for key, val in kwds.items():
                (tmp_path / key).write_text(val)

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
        assert keys1 == keys2

        for key, desired in desired_mapping.items():
            got = given_mapping[key]
            # sanity check the desired data, occasionally screw this up
            assert not isinstance(desired, bare_kls), f"key {key!r}, bad test invocation; " \
                f"bare {bare_kls.__name__} instead of a tuple; val {got!r}"
            assert isinstance(got, tuple), f"key {key!r}, non tuple: {got!r}"
            assert not isinstance(got, bare_kls), f"key {key!r}, bare {bare_kls.__name__}, " \
                f"rather than tuple: {got!r}"
            assert all(isinstance(x, bare_kls) for x in got), \
                f"non {bare_kls.__name__} instance: key {key!r}, got {got!r}; types {list(map(type, got))}"
            got2, desired2 = tuple(map(reformat_f, got)), tuple(map(reformat_f, desired))
            assert got2 == desired2



empty = ((), ())

class TestPmsProfileNode(profile_mixin):

    klass = staticmethod(ProfileNode)
    profile = "default"

    def setup_repo(self, tmp_path):
        ...

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.mk_profile(tmp_path, self.profile)
        self.setup_repo(tmp_path)

    def wipe_path(self, path):
        try:
            shutil.rmtree(path)
        except NotADirectoryError:
            os.unlink(path)
        except FileNotFoundError:
            return

    def write_file(self, tmp_path, filename, text, profile=None):
        (tmp_path / (profile or self.profile) / filename).write_text(text)

    def parsing_checks(self, tmp_path, filename, attr, data=""):
        path = tmp_path / self.profile
        self.write_file(tmp_path, filename, data)
        getattr(self.klass(path), attr)
        self.write_file(tmp_path, filename,  "-")
        self.wipe_path(path / filename)

    def simple_eapi_awareness_check(self, tmp_path, filename, attr,
            bad_data="dev-util/diffball\ndev-util/bsdiff:1",
            good_data="dev-util/diffball\ndev-util/bsdiff"):
        # validate unset eapi=0 prior
        self.parsing_checks(tmp_path, filename, attr, data=good_data)
        self.write_file(tmp_path, "eapi", "1")
        self.parsing_checks(tmp_path, filename, attr, data=good_data)
        self.parsing_checks(tmp_path, filename, attr, data=bad_data)
        self.write_file(tmp_path, "eapi", "0")
        self.wipe_path(tmp_path / self.profile / "eapi")

    def test_eapi(self, tmp_path):
        path = tmp_path / self.profile
        assert str(self.klass(path).eapi) == '0'
        self.write_file(tmp_path, "eapi", "1")
        assert str(self.klass(path).eapi) == '1'

    def test_packages(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).system == empty
        self.parsing_checks(tmp_path, "packages", "system")
        self.write_file(tmp_path, "packages", "#foo\n")
        assert self.klass(path).system == empty
        self.write_file(tmp_path, "packages", "#foo\ndev-util/diffball\n")
        assert self.klass(path).system == empty

        self.write_file(tmp_path, "packages", "-dev-util/diffball\ndev-foo/bar\n*dev-sys/atom\n"
            "-*dev-sys/atom2\nlock-foo/dar")
        assert self.klass(path).system == ((atom("dev-sys/atom2"),), (atom("dev-sys/atom"),))
        self.simple_eapi_awareness_check(tmp_path, 'packages', 'system')

    def test_deprecated(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).deprecated is None
        self.write_file(tmp_path, "deprecated", "")
        assert self.klass(path).deprecated is None
        self.write_file(tmp_path, "deprecated", "foon\n#dar\nfasd")
        assert list(self.klass(path).deprecated) == ["foon", "dar\nfasd"]

    def test_pkg_provided(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).pkg_provided == ((), ())
        self.parsing_checks(tmp_path, "package.provided", "pkg_provided")
        self.write_file(tmp_path, "package.provided", "-dev-util/diffball-1.0")
        assert self.klass(path).pkg_provided == ((CPV.versioned("dev-util/diffball-1.0"),), ())
        self.write_file(tmp_path, "package.provided", "dev-util/diffball-1.0")
        assert self.klass(path).pkg_provided ==  ((), (CPV.versioned("dev-util/diffball-1.0"),))

    def test_masks(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).masks == empty
        self.parsing_checks(tmp_path, "package.mask", "masks")
        self.write_file(tmp_path, "package.mask", "dev-util/diffball")
        assert self.klass(path).masks == ((), (atom("dev-util/diffball"),))
        self.write_file(tmp_path, "package.mask", "-dev-util/diffball")
        assert self.klass(path).masks == ((atom("dev-util/diffball"),), ())
        self.simple_eapi_awareness_check(tmp_path, 'package.mask', 'masks')

    def test_unmasks(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).unmasks == ((), ())
        self.parsing_checks(tmp_path, "package.unmask", "unmasks")
        self.write_file(tmp_path, "package.unmask", "dev-util/diffball")
        assert self.klass(path).unmasks == ((), (atom("dev-util/diffball"),))
        self.write_file(tmp_path, "package.unmask", "-dev-util/diffball")
        assert self.klass(path).unmasks == ((atom("dev-util/diffball"),), ())
        self.simple_eapi_awareness_check(tmp_path, 'package.unmask', 'unmasks')

    def test_pkg_deprecated(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).pkg_deprecated == ((), ())
        self.parsing_checks(tmp_path, "package.deprecated", "pkg_deprecated")
        self.write_file(tmp_path, "package.deprecated", "dev-util/diffball")
        assert self.klass(path).pkg_deprecated == ((), (atom("dev-util/diffball"),))
        self.write_file(tmp_path, "package.deprecated", "-dev-util/diffball")
        assert self.klass(path).pkg_deprecated == ((atom("dev-util/diffball"),), ())
        self.simple_eapi_awareness_check(tmp_path, 'package.deprecated', 'pkg_deprecated')

    def _check_package_use_files(self, tmp_path, caplog, path, filename, attr):
        self.write_file(tmp_path, filename, "dev-util/bar X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
           {"dev-util/bar":(chunked_data(atom("dev-util/bar"), (), ('X',)),)})

        caplog.clear()
        self.write_file(tmp_path, filename, "-dev-util/bar X")
        getattr(self.klass(path), attr) # illegal atom, but only a log is thrown
        assert "invalid package atom: '-dev-util/bar'" in caplog.text

        # verify collapsing optimizations
        self.write_file(tmp_path, filename, "dev-util/foo X\ndev-util/foo X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})

        self.write_file(tmp_path, filename, "d-u/a X\n=d-u/a-1 X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),)})

        self.write_file(tmp_path, filename, "d-u/a X\n=d-u/a-1 -X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),
                chunked_data(atom("=d-u/a-1"), ('X',), ()),)})

        self.write_file(tmp_path, filename, "=d-u/a-1 X\nd-u/a X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
            {"d-u/a":(chunked_data(atom("d-u/a"), (), ('X',)),)})

        self.write_file(tmp_path, filename, "dev-util/bar -X\ndev-util/foo X")
        self.assertEqualChunks(getattr(self.klass(path), attr),
           {"dev-util/bar":(chunked_data(atom("dev-util/bar"), ('X',), ()),),
           "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})

        caplog.clear()
        self.write_file(tmp_path, filename, "dev-util/diffball")
        getattr(self.klass(path), attr) # missing use flag, but only a log is thrown
        assert "missing USE flag(s): 'dev-util/diffball'" in caplog.text

    def test_pkg_keywords(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).keywords == ()
        self.parsing_checks(tmp_path, "package.keywords", "keywords")

        self.write_file(tmp_path, "package.keywords", "dev-util/foo amd64")
        assert self.klass(path).keywords == ((atom("dev-util/foo"), ("amd64",)),)

        self.write_file(tmp_path, "package.keywords", "")
        assert self.klass(path).keywords == ()

        self.write_file(tmp_path, "package.keywords", ">=dev-util/foo-2 -amd64 ~amd64")
        assert self.klass(path).keywords == ((atom(">=dev-util/foo-2"), ("-amd64", "~amd64")),)

    def test_pkg_accept_keywords(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).accept_keywords == ()
        self.parsing_checks(tmp_path, "package.accept_keywords", "accept_keywords")
        self.write_file(tmp_path, "package.accept_keywords", "mmx")

        self.write_file(tmp_path, "package.accept_keywords", "dev-util/foo ~amd64")
        assert self.klass(path).accept_keywords == ((atom("dev-util/foo"), ("~amd64",)),)

        self.write_file(tmp_path, "package.accept_keywords", "")
        assert self.klass(path).accept_keywords == ()

        self.write_file(tmp_path, "package.accept_keywords", "dev-util/bar **")
        assert self.klass(path).accept_keywords == ((atom("dev-util/bar"), ("**",)),)

        self.write_file(tmp_path, "package.accept_keywords", "dev-util/baz")
        assert self.klass(path).accept_keywords == ((atom("dev-util/baz"), ()),)

    def test_masked_use(self, tmp_path, caplog):
        path = tmp_path / self.profile
        self.assertEqualChunks(self.klass(path).masked_use, {})
        self.parsing_checks(tmp_path, "package.use.mask", "masked_use")
        self.parsing_checks(tmp_path, "use.mask", "masked_use")
        self.write_file(tmp_path, "use.mask", "")

        self._check_package_use_files(tmp_path, caplog, path, "package.use.mask", 'masked_use')

        self.write_file(tmp_path, "package.use.mask", "dev-util/bar -X\ndev-util/foo X")

        self.write_file(tmp_path, "use.mask", "mmx")
        self.assertEqualChunks(self.klass(path).masked_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue:(chunked_data(packages.AlwaysTrue, (), ("mmx",)),),
        })

        self.write_file(tmp_path, "use.mask", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).masked_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X', 'foon'), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx',)),),
            atrue: (chunked_data(packages.AlwaysTrue, ('foon',), ('mmx',)),),
        })

        # verify that use.mask is layered first, then package.use.mask
        self.write_file(tmp_path, "package.use.mask", "dev-util/bar -mmx foon")
        self.assertEqualChunks(self.klass(path).masked_use, {
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),),
        })

        self.write_file(tmp_path, "package.use.mask", "")
        self.assertEqualChunks(self.klass(path).masked_use,
           {atrue:(chunked_data(atrue, ('foon',),('mmx',)),)})
        self.simple_eapi_awareness_check(tmp_path, 'package.use.mask', 'masked_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

    def test_stable_masked_use(self, tmp_path, caplog):
        path = tmp_path / self.profile
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})

        # use.stable.mask/package.use.stable.mask only >= EAPI 5
        self.write_file(tmp_path, "use.stable.mask", "mmx")
        self.write_file(tmp_path, "package.use.stable.mask", "dev-util/bar mmx")
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})
        self.wipe_path(path / 'use.stable.mask')
        self.wipe_path(path / 'package.use.stable.mask')

        self.simple_eapi_awareness_check(tmp_path, 'package.use.stable.mask', 'stable_masked_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

        self.write_file(tmp_path, "eapi", "5")
        self.assertEqualChunks(self.klass(path).stable_masked_use, {})
        self.parsing_checks(tmp_path, "package.use.stable.mask", "stable_masked_use")
        self.parsing_checks(tmp_path, "use.stable.mask", "stable_masked_use")

        self._check_package_use_files(tmp_path, caplog, path, "package.use.stable.mask", 'stable_masked_use')

        self.write_file(tmp_path, "package.use.stable.mask", "dev-util/bar -X\ndev-util/foo X")

        self.write_file(tmp_path, "use.stable.mask", "mmx")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue:(chunked_data(packages.AlwaysTrue, (), ("mmx",)),)
            })

        self.write_file(tmp_path, "use.stable.mask", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {"dev-util/bar":
                (chunked_data(atom("dev-util/bar"), ('X', 'foon'), ('mmx',)),),
            "dev-util/foo":
                (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx',)),),
            atrue:(chunked_data(packages.AlwaysTrue, ('foon',), ('mmx',)),)
            })

        # verify that use.stable.mask is layered first, then package.use.stable.mask
        self.write_file(tmp_path, "package.use.stable.mask", "dev-util/bar -mmx foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
            {atrue:(chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar":(chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),)
            })

        self.write_file(tmp_path, "package.use.stable.mask", "")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {atrue:(chunked_data(atrue, ('foon',),('mmx',)),)})

        # verify that settings stack in the following order:
        # use.mask -> use.stable.mask -> package.use.mask -> package.use.stable.mask
        self.write_file(tmp_path, "use.mask", "mmx")
        self.write_file(tmp_path, "use.stable.mask", "-foon")
        self.write_file(tmp_path, "package.use.mask", "dev-util/foo -mmx")
        self.write_file(tmp_path, "package.use.stable.mask", "dev-util/bar foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon', 'mmx'), ()),),
           "dev-util/bar":
               (chunked_data(atom("dev-util/bar"), (), ('foon', 'mmx')),),
           atrue:(chunked_data(atrue, ('foon',), ('mmx',)),)
           })

        self.write_file(tmp_path, "use.mask", "-mmx")
        self.write_file(tmp_path, "use.stable.mask", "foon")
        self.write_file(tmp_path, "package.use.mask", "dev-util/foo mmx")
        self.write_file(tmp_path, "package.use.stable.mask", "dev-util/foo -foon")
        self.assertEqualChunks(self.klass(path).stable_masked_use,
           {"dev-util/foo":
               (chunked_data(atom("dev-util/foo"), ('foon',), ('mmx',)),),
           atrue:(chunked_data(atrue, ('mmx',), ('foon',)),)
           })

    def test_forced_use(self, tmp_path, caplog):
        path = tmp_path / self.profile
        self.assertEqualChunks(self.klass(path).forced_use, {})
        self.parsing_checks(tmp_path, "package.use.force", "forced_use")
        self.parsing_checks(tmp_path, "use.force", "forced_use")
        self.write_file(tmp_path, "use.force", "")

        self._check_package_use_files(tmp_path, caplog, path, "package.use.force", 'forced_use')

        self.write_file(tmp_path, "package.use.force", "dev-util/bar -X\ndev-util/foo X")

        self.write_file(tmp_path, "use.force", "mmx")
        self.assertEqualChunks(self.klass(path).forced_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue: (chunked_data(atrue, (), ('mmx',)),),
        })

        self.write_file(tmp_path, "use.force", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).forced_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X', 'foon',), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx')),),
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
        })

        # verify that use.force is layered first, then package.use.force
        self.write_file(tmp_path, "package.use.force", "dev-util/bar -mmx foon")
        p = self.klass(path)
        self.assertEqualChunks(self.klass(path).forced_use, {
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),),
        })

        self.write_file(tmp_path, "package.use.force", "")
        self.assertEqualChunks(self.klass(path).forced_use, {
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
        })
        self.simple_eapi_awareness_check(tmp_path, 'package.use.force', 'forced_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

    def test_stable_forced_use(self, tmp_path, caplog):
        path = tmp_path / self.profile
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})

        # use.stable.force/package.use.stable.force only >= EAPI 5
        self.write_file(tmp_path, "use.stable.force", "mmx")
        self.write_file(tmp_path, "package.use.stable.force", "dev-util/bar mmx")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})
        self.wipe_path(path / 'use.stable.force')
        self.wipe_path(path / 'package.use.stable.force')

        self.simple_eapi_awareness_check(tmp_path, 'package.use.stable.force', 'stable_forced_use',
           bad_data='=de/bs-1:1 x\nda/bs y',
           good_data='=de/bs-1 x\nda/bs y')

        self.write_file(tmp_path, "eapi", "5")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {})
        self.parsing_checks(tmp_path, "package.use.stable.force", "stable_forced_use")
        self.parsing_checks(tmp_path, "use.stable.force", "stable_forced_use")

        self._check_package_use_files(tmp_path, caplog, path, "package.use.stable.force", 'stable_forced_use')

        self.write_file(tmp_path, "package.use.stable.force", "dev-util/bar -X\ndev-util/foo X")

        self.write_file(tmp_path, "use.stable.force", "mmx")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X',), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ('X', 'mmx')),),
            atrue: (chunked_data(atrue, (), ('mmx',)),),
        })

        self.write_file(tmp_path, "use.stable.force", "mmx\n-foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X', 'foon',), ('mmx',)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('foon',), ('X', 'mmx')),),
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
        })

        # verify that use.stable.force is layered first, then package.use.stable.force
        self.write_file(tmp_path, "package.use.stable.force", "dev-util/bar -mmx foon")
        p = self.klass(path)
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('mmx',), ('foon',)),),
        })

        self.write_file(tmp_path, "package.use.stable.force", "")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),),
        })

        # verify that settings stack in the following order:
        # use.force -> use.stable.force -> package.use.force -> package.use.stable.force
        self.write_file(tmp_path, "use.force", "mmx")
        self.write_file(tmp_path, "use.stable.force", "-foon")
        self.write_file(tmp_path, "package.use.force", "dev-util/foo -mmx")
        self.write_file(tmp_path, "package.use.stable.force", "dev-util/bar foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('foon', 'mmx'), ()),),
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), (), ('foon', 'mmx')),),
            atrue: (chunked_data(atrue, ('foon',), ('mmx',)),)
        })

        self.write_file(tmp_path, "use.force", "-mmx")
        self.write_file(tmp_path, "use.stable.force", "foon")
        self.write_file(tmp_path, "package.use.force", "dev-util/foo mmx")
        self.write_file(tmp_path, "package.use.stable.force", "dev-util/foo -foon")
        self.assertEqualChunks(self.klass(path).stable_forced_use, {
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('foon',), ('mmx',)),),
            atrue: (chunked_data(atrue, ('mmx',), ('foon',)),),
        })

    def test_pkg_use(self, tmp_path, caplog):
        path = tmp_path / self.profile
        self.assertEqualChunks(self.klass(path).pkg_use, {})
        self.parsing_checks(tmp_path, "package.use", "pkg_use")

        self._check_package_use_files(tmp_path, caplog, path, "package.use", 'pkg_use')

        self.write_file(tmp_path, "package.use", "dev-util/bar -X\ndev-util/foo X")
        self.assertEqualChunks(self.klass(path).pkg_use, {
            "dev-util/bar": (chunked_data(atom("dev-util/bar"), ('X',), ()),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),)})
        self.simple_eapi_awareness_check(tmp_path, 'package.use', 'pkg_use',
            bad_data='=de/bs-1:1 x\nda/bs y',
            good_data='=de/bs-1 x\nda/bs y')

    def test_parents(self, tmp_path):
        path = tmp_path / self.profile
        (path / 'child').mkdir()
        self.write_file(tmp_path, "parent", "..", profile=f"{self.profile}/child")
        p = self.klass(path / "child")
        assert len(p.parents) == 1
        assert p.parents[0].path == str(path)

    def test_default_env(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).default_env == {}
        self.write_file(tmp_path, "make.defaults", "X=foo\n")
        assert self.klass(path).default_env == {'X':'foo'}
        self.write_file(tmp_path, 'make.defaults', 'y=narf\nx=${y}\n')
        assert self.klass(path).default_env == {'y':'narf', 'x':'narf'}
        # ensure make.defaults can access the proceeding env.
        (child := tmp_path / self.profile / 'child').mkdir()
        self.write_file(tmp_path, 'make.defaults', 'x="${x} twice"', profile=child)
        self.write_file(tmp_path, 'parent', '..', profile=child)
        assert self.klass(child).default_env == {'y':'narf', 'x':'narf twice'}

    def test_default_env_incrementals(self, tmp_path):
        assert "USE" in const.incrementals
        profile1 = tmp_path / self.profile
        (profile2 := profile1 / "sub").mkdir()
        (profile3 := profile2 / "sub").mkdir()
        self.write_file(tmp_path, "make.defaults", 'USE=foo', profile=profile1)
        self.write_file(tmp_path, "make.defaults", 'x=dar', profile=profile2)
        self.write_file(tmp_path, "parent", "..", profile=profile2)
        self.write_file(tmp_path, "make.defaults", 'USE=-foo', profile=profile3)
        self.write_file(tmp_path, "parent", "..", profile=profile3)
        assert self.klass(profile1).default_env == dict(USE="foo")
        assert self.klass(profile2).default_env == dict(USE="foo", x="dar")
        assert self.klass(profile3).default_env == dict(USE="foo -foo", x="dar")

    def test_bashrc(self, tmp_path):
        path = tmp_path / self.profile
        assert self.klass(path).bashrc is None
        self.write_file(tmp_path, "profile.bashrc", '')
        assert self.klass(path).bashrc is not None


class TestPortage1ProfileNode(TestPmsProfileNode):

    can_be_dirs = frozenset([
        "package.accept_keywords", "package.keywords",
        "package.mask", "package.provided", "package.unmask",
        "package.use", "package.use.force", "package.use.mask",
        "package.use.stable.force", "package.use.stable.mask",
        "use.force", "use.mask", "use.stable.mask", "use.stable.force"
    ])

    klass = partial(TestPmsProfileNode.klass, pms_strict=False)

    def write_file(self, tmp_path, filename, text, profile=None):
        if filename not in self.can_be_dirs:
            return super().write_file(tmp_path, filename, text, profile=profile)
        if profile is None:
            profile = self.profile
        base = tmp_path / profile / filename
        if base.exists():
            self.wipe_path(base)
        base.mkdir()

        for idx, data in enumerate(text.split("\n")):
            (base / str(idx)).write_text(data)

    def test_skip_dotfiles(self, tmp_path):
        path = tmp_path / self.profile

        self.write_file(tmp_path, "package.keywords", "dev-util/foo amd64")
        (path / "package.keywords" / ".test").write_text('dev-util/foo x86')
        assert self.klass(path).keywords == ((atom("dev-util/foo"), ("amd64",)),)

        self.write_file(tmp_path, "package.keywords", "")
        (path / "package.keywords" / ".test").write_text('dev-util/foo x86')
        assert not self.klass(path).keywords


class TestPortage2ProfileNode(TestPortage1ProfileNode):

    profile = os.path.join("profiles", "default")

    def setup_repo(self, tmp_path):
        (tmp_path / "profiles" / "repo_name").write_bytes(binascii.b2a_hex(os.urandom(10)))
        (tmp_path / "metadata").mkdir()
        (tmp_path / "metadata" / "layout.conf").write_text("masters = ''\nprofile-formats = portage-2")


class TestProfileSetProfileNode(TestPmsProfileNode):

    profile = os.path.join("profiles", "default")

    def setup_repo(self, tmp_path):
        (tmp_path / "profiles" / "repo_name").write_bytes(binascii.b2a_hex(os.urandom(10)))
        (tmp_path / "metadata").mkdir()
        (tmp_path / "metadata" / "layout.conf").write_text("masters = ''\nprofile-formats = profile-set")

    def test_packages(self, tmp_path):
        self.write_file(tmp_path, "packages", "dev-sys/atom\n-dev-sys/atom2\n")
        p = self.klass(tmp_path / self.profile)
        assert p.profile_set == ((atom("dev-sys/atom2"),), (atom("dev-sys/atom"),))


class TestOnDiskProfile(profile_mixin):

    # use a derivative, using the inst caching disabled ProfileNode kls
    # from above
    class kls(profiles.OnDiskProfile):
        _node_kls = ProfileNode

    def get_profile(self, tmp_path, profile, basepath=None, **kwds):
        config = central.ConfigManager()
        return self.kls(str(basepath or tmp_path), profile, config, **kwds)

    def test_stacking(self, tmp_path):
        self.mk_profiles(tmp_path,
            {},
            {}
        )
        base = self.get_profile(tmp_path, "0")
        assert [x.path for x in base.stack] == [str(tmp_path), str(tmp_path / "0")]
        assert len(base.system) == 0
        assert len(base.masks) == 0
        assert not base.default_env
        assert not base.masked_use
        assert not base.forced_use
        assert len(base.bashrc) == 0

    def test_packages(self, tmp_path):
        self.mk_profiles(tmp_path,
            {"packages":"*dev-util/diffball\ndev-util/foo\ndev-util/foo2\n"},
            {"packages":"*dev-util/foo\n-*dev-util/diffball\n-dev-util/foo2\n"},
            {"packages":"*dev-util/foo\n", "parent":"0"},
            {"packages":"-*\n*dev-util/foo\n", "parent":"0"},
            {"packages":"*dev-util/foo\n-*\n", "parent":"0"},
            {"packages":"-*\n", "parent":"0"},
        )
        p = self.get_profile(tmp_path, "0")
        assert sorted(p.system) == sorted([atom("dev-util/diffball")])
        assert not sorted(p.masks)

        p = self.get_profile(tmp_path, "1")
        assert sorted(p.system) == sorted([atom("dev-util/foo")])
        assert not sorted(p.masks)

        p = self.get_profile(tmp_path, "2")
        assert sorted(p.system) == sorted([atom("dev-util/diffball"), atom("dev-util/foo")])

        p = self.get_profile(tmp_path, "3")
        assert sorted(p.system) == sorted([atom("dev-util/foo")])

        p = self.get_profile(tmp_path, "4")
        assert sorted(p.system) == sorted([atom("dev-util/foo")])

        p = self.get_profile(tmp_path, "5")
        assert p.system == frozenset()

    def test_masks(self, tmp_path):
        self.mk_profiles(tmp_path,
            {"package.mask":"dev-util/foo"},
            {},
            {"package.mask":"-dev-util/confcache\ndev-util/foo"},
            **{"package.mask":"dev-util/confcache"}
        )
        assert sorted(self.get_profile(tmp_path, "0").masks) == sorted(atom("dev-util/" + x) for x in ["confcache", "foo"])
        assert sorted(self.get_profile(tmp_path, "1").masks) == sorted(atom("dev-util/" + x) for x in ["confcache", "foo"])
        assert sorted(self.get_profile(tmp_path, "2").masks) == [atom("dev-util/foo")]

    def test_unmasks(self, tmp_path):
        self.mk_profiles(tmp_path,
            {"package.unmask":"dev-util/foo"},
            {},
            {"package.unmask":"dev-util/confcache"}
        )
        assert self.get_profile(tmp_path, "0").unmasks == frozenset([atom("dev-util/foo")])
        assert self.get_profile(tmp_path, "1").unmasks == frozenset([atom("dev-util/foo")])
        assert self.get_profile(tmp_path, "2").unmasks == frozenset([atom("dev-util/" + x) for x in ("confcache", "foo")])

    def test_pkg_deprecated(self, tmp_path):
        self.mk_profiles(tmp_path,
            {"package.deprecated":"dev-util/foo"},
            {},
            {"package.deprecated":"dev-util/confcache"}
        )
        assert self.get_profile(tmp_path, "0").pkg_deprecated == frozenset([atom("dev-util/foo")])
        assert self.get_profile(tmp_path, "1").pkg_deprecated == frozenset([atom("dev-util/foo")])
        assert self.get_profile(tmp_path, "2").pkg_deprecated == frozenset([atom("dev-util/" + x) for x in ("confcache", "foo")])

    def test_bashrc(self, tmp_path):
        self.mk_profiles(tmp_path,
            {"profile.bashrc":""},
            {},
            {"profile.bashrc":""}
        )
        assert len(self.get_profile(tmp_path, "0").bashrc) == 1
        assert len(self.get_profile(tmp_path, "1").bashrc) == 1
        assert len(self.get_profile(tmp_path, "2").bashrc) == 2

    def test_pkg_keywords(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        assert not self.get_profile(tmp_path, "0").keywords

        self.mk_profiles(tmp_path,
            {"package.keywords": "dev-util/foo amd64"},
            {},
            {"package.keywords": ">=dev-util/foo-2 -amd64 ~amd64"}
        )
        assert self.get_profile(tmp_path, "0").keywords == ((atom("dev-util/foo"), ("amd64",)),)
        assert self.get_profile(tmp_path, "1").keywords == ((atom("dev-util/foo"), ("amd64",)),)
        assert self.get_profile(tmp_path, "2").keywords == ((atom("dev-util/foo"), ("amd64",)),
            (atom(">=dev-util/foo-2"), ("-amd64", "~amd64")))

    def test_pkg_accept_keywords(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        assert not self.get_profile(tmp_path, "0").accept_keywords

        self.mk_profiles(tmp_path,
            {"package.accept_keywords": "dev-util/foo ~amd64"},
            {},
            {"package.accept_keywords": "dev-util/bar **"},
            {"package.accept_keywords": "dev-util/baz"}
        )
        assert self.get_profile(tmp_path, "0").accept_keywords == ((atom("dev-util/foo"), ("~amd64",)),)
        assert self.get_profile(tmp_path, "1").accept_keywords == ((atom("dev-util/foo"), ("~amd64",)),)
        assert self.get_profile(tmp_path, "2").accept_keywords == ((atom("dev-util/foo"), ("~amd64",)),
            (atom("dev-util/bar"), ("**",)))
        assert self.get_profile(tmp_path, "3").accept_keywords == ((atom("dev-util/foo"), ("~amd64",)),
            (atom("dev-util/bar"), ("**",)),
            (atom("dev-util/baz"), ()))

    def test_masked_use(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        self.assertEqualPayload(self.get_profile(tmp_path, "0").masked_use, {})

        self.mk_profiles(tmp_path,
            {"use.mask":"X\nmmx\n"},
            {},
            {"use.mask":"-X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})

        self.assertEqualPayload(self.get_profile(tmp_path, "1").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx',)),)})

        self.assertEqualPayload(self.get_profile(tmp_path, "2").masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})


        self.mk_profiles(tmp_path,
            {"use.mask":"X\nmmx\n", "package.use.mask":"dev-util/foo cups"},
            {"package.use.mask": "dev-util/foo -cups"},
            {"use.mask":"-X", "package.use.mask": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "cups", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "1").masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "2").masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X', 'cups'), ("mmx",)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ("X", "mmx",)),)
            })

        self.mk_profiles(tmp_path,
            {"use.mask":"X", "package.use.mask":"dev-util/foo -X"},
            {"use.mask":"X"},
            {"package.use.mask":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('X',), ()),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").masked_use,
            {atrue:(chunked_data(atrue, (), ("X")),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),)
            })

        # pkgcore bug 237; per PMS, later profiles can punch wholes in the
        # ranges applicable.
        self.mk_profiles(tmp_path,
            {"package.use.mask":"dev-util/foo X"},
            {"package.use.mask":">=dev-util/foo-1 -X"},
            {"package.use.mask":">=dev-util/foo-2 X"},
            {"package.use.mask":"dev-util/foo X", "name":"collapse_p"},
            {"package.use.mask":"dev-util/foo -X", "parent":"2", "name":"collapse_n"},
            )

        self.assertEqualPayload(self.get_profile(tmp_path, "collapse_p").masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "collapse_n").masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),),
            })

    def test_stable_masked_use(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_masked_use, {})

        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.mask":"X\nmmx\n"},
            {"eapi":"5"},
            {"eapi":"5", "use.stable.mask":"-X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})

        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx',)),)})

        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.mask":"X\nmmx\n", "package.use.stable.mask":"dev-util/foo cups"},
            {"eapi":"5", "package.use.stable.mask": "dev-util/foo -cups"},
            {"eapi":"5", "use.stable.mask":"-X", "package.use.stable.mask": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "cups", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_masked_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X', 'cups'), ("mmx",)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ("X", "mmx",)),)
            })

        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.mask":"X", "package.use.stable.mask":"dev-util/foo -X"},
            {"eapi":"5", "use.stable.mask":"X"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), ('X',), ()),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo": (chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_masked_use,
            {atrue:(chunked_data(atrue, (), ("X")),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),)
            })

        # pkgcore bug 237; per PMS, later profiles can punch wholes in the
        # ranges applicable.
        self.mk_profiles(tmp_path,
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo X"},
            {"eapi":"5", "package.use.stable.mask":">=dev-util/foo-1 -X"},
            {"eapi":"5", "package.use.stable.mask":">=dev-util/foo-2 X"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo X", "name":"collapse_p"},
            {"eapi":"5", "package.use.stable.mask":"dev-util/foo -X", "parent":"2", "name":"collapse_n"},
            )

        self.assertEqualPayload(self.get_profile(tmp_path, "collapse_p").stable_masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X",)),)
            })

        self.assertEqualPayload(self.get_profile(tmp_path, "collapse_n").stable_masked_use,
            {"dev-util/foo":(chunked_data(atom("dev-util/foo"), ("X",), (),),),
            })

    def test_forced_use(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        self.assertEqualPayload(self.get_profile(tmp_path, "0").forced_use, {})
        self.mk_profiles(tmp_path,
            {"use.force":"X\nmmx\n"},
            {},
            {"use.force":"-X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile(tmp_path, "1").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile(tmp_path, "2").forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(tmp_path,
            {"use.force":"X\nmmx\n", "package.use.force":"dev-util/foo cups"},
            {"package.use.force": "dev-util/foo -cups"},
            {"use.force":"-X", "package.use.force": "dev-util/blah X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "mmx", "cups",)),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups', 'X'), ('mmx',)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ('X', "mmx")),),
            })

        self.mk_profiles(tmp_path,
            {"use.force":"X", "package.use.force":"dev-util/foo -X"},
            {"use.force":"X"},
            {"package.use.force":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })

    def test_stable_forced_use(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_forced_use, {})
        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.force":"X\nmmx\n"},
            {"eapi":"5"},
            {"eapi":"5", "use.stable.force":"-X"}
        )

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),)})
        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),)})

        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.force":"X\nmmx\n", "package.use.stable.force":"dev-util/foo cups"},
            {"eapi":"5", "package.use.stable.force":"dev-util/foo -cups"},
            {"eapi":"5", "use.stable.force":"-X", "package.use.stable.force":"dev-util/blah X"}
        )

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ("X", "mmx", "cups",)),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ('X', 'mmx')),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups',), ("X", "mmx")),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_forced_use,
            {atrue:(chunked_data(atrue, ('X',), ('mmx',)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('cups', 'X'), ('mmx',)),),
            "dev-util/blah":(chunked_data(atom("dev-util/blah"), (), ('X', "mmx")),),
            })

        self.mk_profiles(tmp_path,
            {"eapi":"5", "use.stable.force":"X", "package.use.stable.force":"dev-util/foo -X"},
            {"eapi":"5", "use.stable.force":"X"},
            {"eapi":"5", "package.use.stable.force":"dev-util/foo -X"})

        self.assertEqualPayload(self.get_profile(tmp_path, "0").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), (), ('X',)),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").stable_forced_use,
            {atrue:(chunked_data(atrue, (), ("X",)),),
            "dev-util/foo":(chunked_data(atom("dev-util/foo"), ('X',), ()),),
            })

    def test_pkg_use(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        self.assertEqualPayload(self.get_profile(tmp_path, "0").pkg_use, {})
        self.mk_profiles(tmp_path,
            {"package.use":"dev-util/bsdiff X mmx\n"},
            {},
            {"package.use":"dev-util/bsdiff -X\n"},
            {"package.use":"dev-util/bsdiff -mmx\ndev-util/diffball X"},
            {"package.use":"dev-util/bsdiff X\ndev-util/diffball -X\n"}
            )

        self.assertEqualPayload(self.get_profile(tmp_path, "0").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), (), ('X', 'mmx')),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "1").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), (), ('X', 'mmx')),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "2").pkg_use,
            {'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('X',), ('mmx',)),)
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "3").pkg_use,
            {'dev-util/diffball':
                (chunked_data(atom("dev-util/diffball"), (), ('X',)),),
            'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('X', 'mmx'), ()),),
            })
        self.assertEqualPayload(self.get_profile(tmp_path, "4").pkg_use,
            {'dev-util/diffball':
                (chunked_data(atom("dev-util/diffball"), ('X',), ()),),
            'dev-util/bsdiff':
                (chunked_data(atom("dev-util/bsdiff"), ('mmx',), ('X',)),),
            })

    def test_default_env(self, tmp_path):
        assert 'USE' in const.incrementals_unfinalized
        assert 'USE' in const.incrementals
        assert 'USE_EXPAND' in const.incrementals

        # first, verify it behaves correctly for unfinalized incrementals.
        self.mk_profiles(tmp_path, {})
        assert not self.get_profile(tmp_path, "0").default_env
        self.mk_profiles(tmp_path,
            {"make.defaults":"USE=y\n"},
            {},
            {"make.defaults":"USE=-y\nY=foo\n"})
        assert self.get_profile(tmp_path, '0').default_env == {"USE": ('y', )}
        assert self.get_profile(tmp_path, '1').default_env == {"USE": ('y', )}
        assert self.get_profile(tmp_path, '2').default_env == {'Y': 'foo',  "USE": ('y', '-y')}

        # next, verify it optimizes for the finalized incrementals
        self.mk_profiles(tmp_path, {})
        assert not self.get_profile(tmp_path, "0").default_env
        self.mk_profiles(tmp_path,
            {"make.defaults":"USE_EXPAND=y\n"},
            {},
            {"make.defaults":"USE_EXPAND=-y\nY=foo\n"})
        assert self.get_profile(tmp_path, '0').default_env == {"USE_EXPAND": ('y', )}
        assert self.get_profile(tmp_path, '1').default_env == {"USE_EXPAND": ('y', )}
        assert self.get_profile(tmp_path, '2').default_env == {'Y': 'foo'}

    def test_iuse_effective(self, tmp_path, tmp_path_factory):
        # TODO: add subprofiles for testing incrementals
        self.mk_profiles(tmp_path,
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
        repo = tmp_path_factory.mktemp("repo")
        (repo / 'metadata').mkdir()
        (basepath := repo / 'profiles').symlink_to(tmp_path)

        # avoid RepoConfig warnings on initialization
        (repo / 'metadata' / 'layout.conf').write_text('repo-name = test\nmasters = gentoo\n')

        class RepoConfig(repo_objs.RepoConfig):
            # re-inherited to disable inst-caching
            pass

        # disable instance caching on RepoConfig otherwise the known arches
        # value will be cached
        with mock.patch('pkgcore.ebuild.repo_objs.RepoConfig', RepoConfig):
            assert self.get_profile(tmp_path, '0', basepath).iuse_effective == frozenset()
            (basepath / 'arch.list').write_text('amd64\narm\n')
            assert self.get_profile(tmp_path, '0', basepath).iuse_effective == frozenset(['amd64', 'arm'])
            assert self.get_profile(tmp_path, '1', basepath).iuse_effective == frozenset(['amd64', 'arm', 'elibc_glibc', 'elibc_uclibc'])
            assert self.get_profile(tmp_path, '2', basepath).iuse_effective == frozenset(['abi_x86_64', 'foo', 'amd64', 'arm', 'abi_x86_64',
                           'elibc_glibc', 'elibc_uclibc'])

    def test_provides_repo(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        assert len(self.get_profile(tmp_path, "0").provides_repo) == 0

        self.mk_profiles(tmp_path,
            {"package.provided":"dev-util/diffball-0.7.1"})
        assert ["dev-util/diffball-0.7.1"] == [x.cpvstr for x in
            self.get_profile(tmp_path, "0").provides_repo]

        self.mk_profiles(tmp_path,
            {"package.provided":"dev-util/diffball-0.7.1"},
            {"package.provided":
                "-dev-util/diffball-0.7.1\ndev-util/bsdiff-0.4"}
        )
        assert ["dev-util/bsdiff-0.4"] == [x.cpvstr for x in
            sorted(self.get_profile(tmp_path, "1").provides_repo)]

    def test_deprecated(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        assert not self.get_profile(tmp_path, "0").deprecated
        self.mk_profiles(tmp_path,
            {"deprecated":"replacement\nfoon\n"},
            {}
            )
        assert not self.get_profile(tmp_path, "1").deprecated
        self.mk_profiles(tmp_path,
            {},
            {"deprecated":"replacement\nfoon\n"}
            )
        assert self.get_profile(tmp_path, "1").deprecated

    def test_eapi(self, tmp_path):
        self.mk_profiles(tmp_path, {})
        assert str(self.get_profile(tmp_path, "0").eapi) == '0'
        self.mk_profiles(tmp_path, {"eapi": "5\n"})
        assert str(self.get_profile(tmp_path, "0").eapi) == '5'

    def test_from_abspath(self, tmp_path):
        self.mk_profiles(tmp_path, {'name': 'profiles'}, {'name': 'profiles/1'})
        base = tmp_path / 'profiles'
        p = self.kls.from_abspath(str(base / '1'))
        assert p is not None
        assert normpath(p.basepath) == normpath(str(base))
        assert normpath(p.profile) == normpath(str(base / '1'))
