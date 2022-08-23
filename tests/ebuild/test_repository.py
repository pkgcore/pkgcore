import textwrap
from pathlib import Path

import pytest

from pkgcore.ebuild import eclass_cache
from pkgcore.ebuild import repository, restricts
from pkgcore.ebuild.atom import atom
from pkgcore.repository import errors
from snakeoil.contexts import chdir


class TestUnconfiguredTree:

    def mk_tree(self, path, *args, **kwds):
        eclasses = kwds.pop('eclass_cache', None)
        if eclasses is None:
            (epath := path / 'eclass').mkdir(parents=True, exist_ok=True)
            eclasses = eclass_cache.cache(str(epath))
        (path / 'profiles').mkdir(exist_ok=True)
        return repository.UnconfiguredTree(str(path), eclass_cache=eclasses, *args, **kwds)

    @pytest.fixture
    def pdir(self, tmp_path):
        (pdir := tmp_path / 'profiles').mkdir(exist_ok=True)

        # silence missing masters warnings
        if not (tmp_path / 'metadata').exists():
            (tmp_path / 'metadata').mkdir()
            (tmp_path / 'metadata' / 'layout.conf').write_text('masters =\n')

        return pdir

    def test_repo_from_file(self, tmp_path):
        (tmp_path / 'random').write_text('random')
        with pytest.raises(errors.InitializationError):
            return repository.UnconfiguredTree(str(tmp_path / 'random'), eclass_cache=None)

    def test_basics(self, tmp_path, pdir, caplog):
        repo = self.mk_tree(tmp_path)
        # Just make sure these do not raise.
        assert str(repo)
        assert repr(repo)

        caplog.clear()
        self.mk_tree(tmp_path / 'missing')
        assert caplog.text

    def test_thirdpartymirrors(self, tmp_path, pdir):
        (pdir / 'thirdpartymirrors').write_text(textwrap.dedent('''\
            spork http://sporks/ http://moresporks/
            foon foon://foons/
        '''))
        mirrors = self.mk_tree(tmp_path).mirrors
        assert set(mirrors) == {'spork', 'foon'}
        assert set(mirrors['spork']) == {'http://moresporks/', 'http://sporks/'}
        (pdir / 'thirdpartymirrors').write_text("foon  dar\n")
        assert set(self.mk_tree(tmp_path).mirrors.keys()) == {'foon'}

    def test_repo_id(self, tmp_path):
        repo = self.mk_tree(dir1 := tmp_path / '1')
        assert repo.repo_id == str(dir1)

        (dir2 := tmp_path / '2').mkdir(0o755)
        (dir2 / 'profiles').mkdir()
        (dir2 / 'profiles' / 'repo_name').write_text('testrepo\n')
        repo = self.mk_tree(dir2)
        assert repo.repo_id == 'testrepo'

    def test_licenses(self, tmp_path):
        licenses = {'GPL-2', 'GPL-3+', 'BSD'}
        (tmp_path / 'licenses').mkdir()
        for license in licenses:
            (tmp_path / 'licenses' / license).touch()
        repo = self.mk_tree(tmp_path)
        assert set(repo.licenses) == licenses

    def test_masters(self, tmp_path):
        repo = self.mk_tree(tmp_path)
        assert repo.masters == ()

    def test_path_restrict(self, tmp_path, tmp_path_factory):
        repo_dir = tmp_path_factory.mktemp('repo', numbered=True)
        sym_repo_dir = tmp_path_factory.mktemp('sym_repo', numbered=True)
        sym_repo_dir.rmdir()
        sym_repo_dir.symlink_to(repo_dir)

        (repo_dir / 'profiles').mkdir()
        (repo_dir / 'profiles' / 'repo_name').write_text('testrepo\n')
        (repo_dir / 'profiles' / 'categories').write_text('cat\ntac\n')
        (repo_dir / 'skel.ebuild').touch()
        (repo_dir / 'cat' / 'foo').mkdir(parents=True)
        (repo_dir / 'cat' / 'foo' / 'Manifest').touch()
        (repo_dir / 'cat' / 'foo' / 'foo-1.ebuild').write_text('SLOT=0\n')
        (repo_dir / 'cat' / 'foo' / 'foo-2.ebuild').write_text('SLOT=0\n')
        (repo_dir / 'cat' / 'bar').mkdir(parents=True)
        (repo_dir / 'cat' / 'bar' / 'bar-1.ebuild').write_text('SLOT=0\n')
        (repo_dir / 'tac' / 'oof').mkdir(parents=True)
        (repo_dir / 'tac' / 'oof' / 'oof-1.ebuild').write_text('SLOT=0\n')

        for d in (repo_dir, sym_repo_dir):
            repo = self.mk_tree(d)
            location = Path(repo.location)
            for path in (
                tmp_path,  # path not in repo
                location / 'a',  # nonexistent category dir
                # location / 'profiles',  # non-category dir
                location / 'skel.ebuild',  # not in the correct cat/PN dir layout
                location / 'cat' / 'a',  # nonexistent package dir
                location / 'cat' / 'foo' / 'foo-0.ebuild',  # nonexistent ebuild file
                location / 'cat' / 'foo' / 'Manifest',  # non-ebuild file
            ):
                with pytest.raises(ValueError):
                    repo.path_restrict(str(path))

            # repo dir
            restriction = repo.path_restrict(repo.location)
            assert len(restriction) == 1
            assert isinstance(restriction[0], restricts.RepositoryDep)
            # matches all 4 ebuilds in the repo
            assert len(repo.match(restriction)) == 4

            # category dir
            restriction = repo.path_restrict(str(location / 'cat'))
            assert len(restriction) == 2
            assert isinstance(restriction[1], restricts.CategoryDep)
            # matches all 3 ebuilds in the category
            assert len(repo.match(restriction)) == 3

            # relative category dir
            with chdir(repo.location):
                restriction = repo.path_restrict('cat')
                assert len(restriction) == 2
                assert isinstance(restriction[1], restricts.CategoryDep)
                # matches all 3 ebuilds in the category
                assert len(repo.match(restriction)) == 3

            # package dir
            restriction = repo.path_restrict(str(location / 'cat' / 'foo'))
            assert len(restriction) == 3
            assert isinstance(restriction[2], restricts.PackageDep)
            # matches both ebuilds in the package dir
            assert len(repo.match(restriction)) == 2

            # relative package dir
            with chdir(repo.location):
                restriction = repo.path_restrict('cat/foo')
                assert len(restriction) == 3
                assert isinstance(restriction[2], restricts.PackageDep)
                # matches both ebuilds in the package dir
                assert len(repo.match(restriction)) == 2

            # ebuild file
            restriction = repo.path_restrict(str(location / 'cat' / 'foo' / 'foo-1.ebuild'))
            assert len(restriction) == 4
            assert isinstance(restriction[3], restricts.VersionMatch)
            # specific ebuild version match
            assert len(repo.match(restriction)) == 1

            # relative ebuild file path
            with chdir((location / 'cat' / 'foo').resolve()):
                restriction = repo.path_restrict('./foo-1.ebuild')
                assert len(restriction) == 4
                assert isinstance(restriction[3], restricts.VersionMatch)
                # specific ebuild version match
                assert len(repo.match(restriction)) == 1

    def test_categories_packages(self, tmp_path):
        (tmp_path / 'cat' / 'pkg').mkdir(parents=True)
        (tmp_path / 'empty' / 'empty').mkdir(parents=True)
        (tmp_path / 'cat' / 'pkg' / 'pkg-3.ebuild').touch()
        repo = self.mk_tree(tmp_path)
        assert {'cat': (), 'empty': ()} == dict(repo.categories)
        assert {'cat': ('pkg',), 'empty': ('empty',)} == dict(repo.packages)
        assert {('cat', 'pkg'): ('3',), ('empty', 'empty'): ()} == dict(repo.versions)

    def test_package_mask(self, tmp_path, pdir):
        (pdir / 'package.mask').write_text(textwrap.dedent('''\
            # lalala
            it-is/broken
            <just/newer-than-42
        '''))
        repo = self.mk_tree(tmp_path)
        assert set(repo.pkg_masks) == {atom('it-is/broken'), atom('<just/newer-than-42')}


class TestSlavedTree(TestUnconfiguredTree):

    def mk_tree(self, path, *args, **kwds):
        if path != self.dir_slave:
            self.dir_slave = path
            self.dir_master = path.parent / (path.name + 'master')
            (self.dir_slave / 'profiles').mkdir(parents=True, exist_ok=True)
            (self.dir_master / 'profiles').mkdir(parents=True, exist_ok=True)

        eclasses = kwds.pop('eclass_cache', None)
        if eclasses is None:
            (epath := path / 'eclass').mkdir(parents=True, exist_ok=True)
            eclasses = eclass_cache.cache(str(epath))

        self.master_repo = repository.UnconfiguredTree(str(self.dir_master), eclass_cache=eclasses, *args, **kwds)
        masters = (self.master_repo,)
        return repository.UnconfiguredTree(str(self.dir_slave), eclass_cache=eclasses, masters=masters, *args, **kwds)

    @pytest.fixture(autouse=True)
    def master_repo(self, tmp_path_factory):
        self.dir_master = tmp_path_factory.mktemp('master', numbered=True)
        (self.dir_master / 'metadata').mkdir()
        (self.dir_master / 'metadata' / 'layout.conf').write_text('masters =\n')
        (self.dir_master / 'profiles').mkdir()
        (self.dir_master / 'profiles' / 'repo_name').write_text('master\n')
        return self.dir_master

    @pytest.fixture(autouse=True)
    def slave_repo(self, tmp_path):
        self.dir_slave = tmp_path
        (self.dir_slave / 'metadata').mkdir()
        (self.dir_slave / 'metadata' / 'layout.conf').write_text('masters = master\n')
        (self.dir_slave / 'profiles').mkdir()
        (self.dir_slave / 'profiles' / 'repo_name').write_text('slave\n')
        return self.dir_slave

    @pytest.mark.parametrize(("master", "slave", "expected"), (
        (('cat',), (), ('cat',)),
        ((), ('cat',), ('cat',)),
        (('sys-apps', 'foo'), ('cat', 'foo'), ('cat', 'foo', 'sys-apps')),
    ))
    def test_categories(self, master_repo, slave_repo, master, slave, expected):
        # categories are inherited from masters
        (master_repo / 'profiles' / 'categories').write_text('\n'.join(master))
        (slave_repo / 'profiles' / 'categories').write_text('\n'.join(slave))
        for cat in master:
            (master_repo / cat).mkdir(0o755)
        for cat in slave:
            (slave_repo / cat).mkdir(0o755)
        repo = self.mk_tree(slave_repo)
        assert tuple(sorted(repo.categories)) == expected

    def test_licenses(self, master_repo, slave_repo):
        master_licenses = ('GPL-2', 'GPL-3+', 'BSD')
        slave_licenses = ('BSD-2', 'MIT')
        (master_repo / 'licenses').mkdir()
        for license in master_licenses:
            (master_repo / 'licenses' / license).touch()
        (slave_repo / 'licenses').mkdir()
        for license in slave_licenses:
            (slave_repo / 'licenses' / license).touch()
        repo = self.mk_tree(slave_repo)
        assert set(repo.licenses) == set(master_licenses + slave_licenses)

    def test_license_groups(self, master_repo, slave_repo):
        master_licenses = ('GPL-2', 'BSD')
        slave_licenses = ('BSD-2', 'MIT')

        (master_repo / 'licenses').mkdir()
        for license in master_licenses:
            (master_repo / 'licenses' / license).touch()
        (master_repo / 'profiles' / 'license_groups').write_text(f'FREE {" ".join(master_licenses)}\nOSI-APPROVED @FREE\n')

        (slave_repo / 'licenses').mkdir()
        for license in slave_licenses:
            (slave_repo / 'licenses' / license).touch()
        (slave_repo / 'profiles' / 'license_groups').write_text(f'MISC-FREE @FREE {" ".join(slave_licenses)}\nFSF-APPROVED MIT\nOSI-APPROVED @FSF-APPROVED\n')

        repo = self.mk_tree(slave_repo)
        assert set(repo.licenses) == set(master_licenses + slave_licenses)
        assert set(repo.licenses.groups) == {'FREE', 'FSF-APPROVED', 'MISC-FREE', 'OSI-APPROVED'}
        assert 'BSD' in repo.licenses.groups['MISC-FREE']

    def test_package_deprecated(self, slave_repo, master_repo):
        (master_repo / 'profiles' / 'package.deprecated').write_text(textwrap.dedent('''\
            # lalala
            it-is/deprecated
            <just/newer-than-42
        '''))
        repo = self.mk_tree(slave_repo)
        assert set(repo.deprecated) == {atom('it-is/deprecated'), atom('<just/newer-than-42')}

    def test_use_expand_desc(self, slave_repo, master_repo):
        use_expand_desc = {
            'example': (('example_foo', 'Build with foo'),
                        ('example_bar', 'Build with bar'))
        }
        (master_repo / 'profiles' / 'desc').mkdir()
        (master_repo / 'profiles' / 'desc' / 'example').write_text(textwrap.dedent('''\
            foo - Build with foo
            bar - Build with bar
        '''))
        repo = self.mk_tree(slave_repo)
        assert use_expand_desc == dict(repo.use_expand_desc)

    def test_masters(self, slave_repo):
        repo = self.mk_tree(slave_repo)
        assert repo.masters == (self.master_repo,)
