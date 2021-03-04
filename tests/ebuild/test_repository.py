import os
import textwrap
from unittest import mock

from snakeoil.fileutils import touch
from snakeoil.osutils import ensure_dirs, pjoin
from snakeoil.test.mixins import TempDirMixin

from pkgcore.ebuild import eclass_cache
from pkgcore.ebuild import errors as ebuild_errors
from pkgcore.ebuild import repository, restricts
from pkgcore.ebuild.atom import atom
from pkgcore.repository import errors


class TestUnconfiguredTree(TempDirMixin):

    def mk_tree(self, path, *args, **kwds):
        eclasses = kwds.pop('eclass_cache', None)
        if eclasses is None:
            epath = pjoin(path, 'eclass')
            ensure_dirs(epath)
            eclasses = eclass_cache.cache(epath)
        ensure_dirs(pjoin(path, 'profiles'))
        return repository.UnconfiguredTree(path, eclass_cache=eclasses, *args, **kwds)

    def setUp(self):
        TempDirMixin.setUp(self)
        self.pdir = pjoin(self.dir, 'profiles')
        ensure_dirs(self.pdir)

        # silence missing masters warnings
        ensure_dirs(pjoin(self.dir, 'metadata'))
        with open(pjoin(self.dir, 'metadata', 'layout.conf'), 'w') as f:
            f.write('masters =\n')

    def test_basics(self):
        repo = self.mk_tree(self.dir)
        # Just make sure these do not raise.
        self.assertTrue(str(repo))
        self.assertTrue(repr(repo))

        self.assertRaises(
            errors.InitializationError,
            self.mk_tree, pjoin(self.dir, 'missing'))

        with open(pjoin(self.dir, 'random'), 'w') as f:
            f.write('random')
        self.assertRaises(
            errors.InitializationError,
            self.mk_tree, pjoin(self.dir, 'random'))

    def test_thirdpartymirrors(self):
        with open(pjoin(self.pdir, 'thirdpartymirrors'), 'w') as f:
            f.write(textwrap.dedent('''\
                spork http://sporks/ http://moresporks/
                foon foon://foons/
            '''))
        mirrors = self.mk_tree(self.dir).mirrors
        self.assertEqual(['foon', 'spork'], sorted(mirrors))
        self.assertEqual(
            ['http://moresporks/', 'http://sporks/'],
            sorted(mirrors['spork']))
        with open(pjoin(self.pdir, 'thirdpartymirrors'), 'w') as f:
            f.write("foon  dar\n")
        self.assertEqual(list(self.mk_tree(self.dir).mirrors.keys()), ['foon'])

    def test_repo_id(self):
        dir1 = pjoin(self.dir, '1')
        os.mkdir(dir1, 0o755)
        repo = self.mk_tree(dir1)
        self.assertEqual(repo.repo_id, dir1)
        dir2 = pjoin(self.dir, '2')
        ensure_dirs(pjoin(dir2, 'profiles'))
        with open(pjoin(dir2, 'profiles', 'repo_name'), 'w') as f:
            f.write('testrepo\n')
        repo = self.mk_tree(dir2)
        self.assertEqual('testrepo', repo.repo_id)

    def test_licenses(self):
        licenses = ('GPL-2', 'GPL-3+', 'BSD')
        ensure_dirs(pjoin(self.dir, 'licenses'))
        for license in licenses:
            touch(pjoin(self.dir, 'licenses', license))
        repo = self.mk_tree(self.dir)
        self.assertEqual(sorted(repo.licenses), sorted(licenses))

    def test_masters(self):
        repo = self.mk_tree(self.dir)
        self.assertEqual(repo.masters, ())

    def test_path_restrict(self):
        repo_dir = pjoin(self.dir, 'repo')
        sym_repo_dir = pjoin(self.dir, 'sym_repo')
        os.symlink(repo_dir, sym_repo_dir)

        ensure_dirs(pjoin(repo_dir, 'profiles'))
        with open(pjoin(repo_dir, 'profiles', 'repo_name'), 'w') as f:
            f.write('testrepo\n')
        ensure_dirs(pjoin(repo_dir, 'cat', 'foo'))
        ensure_dirs(pjoin(repo_dir, 'cat', 'bar'))
        ensure_dirs(pjoin(repo_dir, 'tac', 'oof'))
        touch(pjoin(repo_dir, 'skel.ebuild'))
        touch(pjoin(repo_dir, 'cat', 'foo', 'Manifest'))
        ebuilds = (
            pjoin(repo_dir, 'cat', 'foo', 'foo-1.ebuild'),
            pjoin(repo_dir, 'cat', 'foo', 'foo-2.ebuild'),
            pjoin(repo_dir, 'cat', 'bar', 'bar-1.ebuild'),
            pjoin(repo_dir, 'tac', 'oof', 'oof-1.ebuild'),
        )
        for ebuild in ebuilds:
            with open(ebuild, 'w') as f:
                f.write('SLOT=0\n')

        # specify repo category dirs
        with open(pjoin(repo_dir, 'profiles', 'categories'), 'w') as f:
            f.write('cat\n')
            f.write('tac\n')

        for d in (repo_dir, sym_repo_dir):
            repo = self.mk_tree(d)
            for path in (
                    self.dir,  # path not in repo
                    pjoin(repo.location, 'a'),  # nonexistent category dir
                    pjoin(repo.location, 'profiles'),  # non-category dir
                    pjoin(repo.location, 'skel.ebuild'),  # not in the correct cat/PN dir layout
                    pjoin(repo.location, 'cat', 'a'),  # nonexistent package dir
                    pjoin(repo.location, 'cat', 'foo', 'foo-0.ebuild'),  # nonexistent ebuild file
                    pjoin(repo.location, 'cat', 'foo', 'Manifest'),  # non-ebuild file
                    ):
                self.assertRaises(ValueError, repo.path_restrict, path)

            # repo dir
            restriction = repo.path_restrict(repo.location)
            self.assertEqual(len(restriction), 1)
            self.assertInstance(restriction[0], restricts.RepositoryDep)
            # matches all 4 ebuilds in the repo
            self.assertEqual(len(repo.match(restriction)), 4)

            # category dir
            restriction = repo.path_restrict(pjoin(repo.location, 'cat'))
            self.assertEqual(len(restriction), 2)
            self.assertInstance(restriction[1], restricts.CategoryDep)
            # matches all 3 ebuilds in the category
            self.assertEqual(len(repo.match(restriction)), 3)

            # relative category dir
            with mock.patch('os.getcwd', return_value=repo.location):
                restriction = repo.path_restrict('cat')
                self.assertEqual(len(restriction), 2)
                self.assertInstance(restriction[1], restricts.CategoryDep)
                # matches all 3 ebuilds in the category
                self.assertEqual(len(repo.match(restriction)), 3)

            # package dir
            restriction = repo.path_restrict(pjoin(repo.location, 'cat', 'foo'))
            self.assertEqual(len(restriction), 3)
            self.assertInstance(restriction[2], restricts.PackageDep)
            # matches both ebuilds in the package dir
            self.assertEqual(len(repo.match(restriction)), 2)

            # relative package dir
            with mock.patch('os.getcwd', return_value=repo.location):
                restriction = repo.path_restrict('cat/foo')
                self.assertEqual(len(restriction), 3)
                self.assertInstance(restriction[2], restricts.PackageDep)
                # matches both ebuilds in the package dir
                self.assertEqual(len(repo.match(restriction)), 2)

            # ebuild file
            restriction = repo.path_restrict(pjoin(repo.location, 'cat', 'foo', 'foo-1.ebuild'))
            self.assertEqual(len(restriction), 4)
            self.assertInstance(restriction[3], restricts.VersionMatch)
            # specific ebuild version match
            self.assertEqual(len(repo.match(restriction)), 1)

            # relative ebuild file path
            with mock.patch('os.getcwd', return_value=os.path.realpath(pjoin(repo.location, 'cat', 'foo'))):
                restriction = repo.path_restrict('./foo-1.ebuild')
                self.assertEqual(len(restriction), 4)
                self.assertInstance(restriction[3], restricts.VersionMatch)
                # specific ebuild version match
                self.assertEqual(len(repo.match(restriction)), 1)

    def test_categories_packages(self):
        ensure_dirs(pjoin(self.dir, 'cat', 'pkg'))
        ensure_dirs(pjoin(self.dir, 'empty', 'empty'))
        ensure_dirs(pjoin(self.dir, 'scripts', 'pkg'))
        ensure_dirs(pjoin(self.dir, 'notcat', 'CVS'))
        touch(pjoin(self.dir, 'cat', 'pkg', 'pkg-3.ebuild'))
        repo = self.mk_tree(self.dir)
        self.assertEqual(
            {'cat': (), 'notcat': (), 'empty': ()}, dict(repo.categories))
        self.assertEqual(
            {'cat': ('pkg',), 'empty': ('empty',), 'notcat': ()},
            dict(repo.packages))
        self.assertEqual(
            {('cat', 'pkg'): ('3',), ('empty', 'empty'): ()},
            dict(repo.versions))

    def test_package_mask(self):
        with open(pjoin(self.pdir, 'package.mask'), 'w') as f:
            f.write(textwrap.dedent('''\
                # lalala
                it-is/broken
                <just/newer-than-42
            '''))
        repo = self.mk_tree(self.dir)
        self.assertEqual(sorted([atom('it-is/broken'),
            atom('<just/newer-than-42')]),
            sorted(repo.pkg_masks))


class TestSlavedTree(TestUnconfiguredTree):

    def mk_tree(self, path, *args, **kwds):
        if path != self.dir:
            self.dir_slave = path
            self.dir_master = pjoin(os.path.dirname(path), os.path.basename(path) + 'master')
            ensure_dirs(self.dir_slave)
            ensure_dirs(self.dir_master)
            ensure_dirs(pjoin(self.dir_slave, 'profiles'))
            ensure_dirs(pjoin(self.dir_master, 'profiles'))

        eclasses = kwds.pop('eclass_cache', None)
        if eclasses is None:
            epath = pjoin(self.dir_master, 'eclass')
            ensure_dirs(epath)
            eclasses = eclass_cache.cache(epath)

        self.master_repo = repository.UnconfiguredTree(self.dir_master, eclass_cache=eclasses, *args, **kwds)
        masters = (self.master_repo,)
        return repository.UnconfiguredTree(self.dir_slave, eclass_cache=eclasses, masters=masters, *args, **kwds)

    def setUp(self):
        TempDirMixin.setUp(self)
        self.dir_orig = self.dir

        self.dir_master = pjoin(self.dir, 'master')
        self.dir_slave = pjoin(self.dir, 'slave')
        ensure_dirs(self.dir_master)
        ensure_dirs(self.dir_slave)

        ensure_dirs(pjoin(self.dir_master, 'metadata'))
        ensure_dirs(pjoin(self.dir_slave, 'metadata'))
        # silence missing masters warnings
        with open(pjoin(self.dir_master, 'metadata', 'layout.conf'), 'w') as f:
            f.write('masters =\n')
        with open(pjoin(self.dir_slave, 'metadata', 'layout.conf'), 'w') as f:
            f.write('masters = master\n')

        self.master_pdir = pjoin(self.dir_master, 'profiles')
        self.pdir = self.slave_pdir = pjoin(self.dir_slave, 'profiles')
        ensure_dirs(self.master_pdir)
        ensure_dirs(self.slave_pdir)
        # silence missing repo name warnings
        with open(pjoin(self.master_pdir, 'repo_name'), 'w') as f:
            f.write('master\n')
        with open(pjoin(self.slave_pdir, 'repo_name'), 'w') as f:
            f.write('slave\n')

        self.dir = self.dir_slave

    def tearDown(self):
        self.dir = self.dir_orig
        TempDirMixin.tearDown(self)

    def _create_categories(self, master, slave, write=True):
        with open(pjoin(self.master_pdir, 'categories'), 'w') as f:
            f.write('\n'.join(master))
        with open(pjoin(self.slave_pdir, 'categories'), 'w') as f:
            f.write('\n'.join(slave))
        for cat in master:
            os.mkdir(pjoin(self.dir_master, cat), 0o755)
        for cat in slave:
            os.mkdir(pjoin(self.dir_slave, cat), 0o755)
        return self.mk_tree(self.dir)

    def test_categories(self):
        # categories are inherited from masters
        for master, slave, expected in (
                (('cat',), (), ('cat',)),
                ((), ('cat',), ('cat',)),
                (('sys-apps', 'foo'), ('cat', 'foo'), ('cat', 'foo', 'sys-apps'))):
            # profiles/categories files exist along with category dirs
            self.setUp()
            repo = self._create_categories(master, slave)
            self.assertEqual(tuple(sorted(repo.categories)), expected)
            self.tearDown()

            # no profiles/categories files created, only category dirs
            self.setUp()
            repo = self._create_categories(master, slave, write=False)
            self.assertEqual(tuple(sorted(repo.categories)), expected)
            self.tearDown()
        self.setUp()

    def test_licenses(self):
        master_licenses = ('GPL-2', 'GPL-3+', 'BSD')
        slave_licenses = ('BSD-2', 'MIT')
        ensure_dirs(pjoin(self.dir_slave, 'licenses'))
        ensure_dirs(pjoin(self.dir_master, 'licenses'))
        for license in master_licenses:
            touch(pjoin(self.dir_master, 'licenses', license))
        for license in slave_licenses:
            touch(pjoin(self.dir_slave, 'licenses', license))
        repo = self.mk_tree(self.dir)
        self.assertEqual(sorted(repo.licenses), sorted(master_licenses + slave_licenses))

    def test_masters(self):
        repo = self.mk_tree(self.dir)
        self.assertEqual(repo.masters, (self.master_repo,))
