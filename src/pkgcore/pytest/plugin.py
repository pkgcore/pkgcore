import os
import subprocess
import textwrap
from collections.abc import MutableSet
from datetime import datetime

from snakeoil import klass
from snakeoil.fileutils import touch
from snakeoil.osutils import pjoin

import pytest


class GitRepo:
    """Class for creating/manipulating git repos.

    Only relies on the git binary existing in order to limit
    dependency requirements.
    """

    def __init__(self, path, bare=False, branch='main', commit=False, clone=False):
        self.path = path
        if clone:
            os.makedirs(self.path)
            self.run(['git', 'clone', clone, self.path])
        else:
            self.run(['git', 'init', '-b', branch] + (['--bare'] if bare else []) + [self.path])
            self.run(['git', 'config', 'user.email', 'first.last@email.com'])
            self.run(['git', 'config', 'user.name', 'First Last'])

        if commit:
            if self.changes:
                # if files exist in the repo, add them in an initial commit
                self.add_all(msg='initial commit')
            else:
                # otherwise add a stub initial commit
                self.add(pjoin(self.path, '.init'), create=True)

    def run(self, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs):
        return subprocess.run(
            cmd, cwd=self.path, encoding='utf8', check=True,
            stdout=stdout, stderr=stderr, **kwargs)

    def log(self, args):
        """Run ``git log`` with given args and return a list of outputted lines."""
        p = self.run(['git', 'log'] + args, stdout=subprocess.PIPE)
        return p.stdout.strip().splitlines()

    @property
    def changes(self):
        """Return a list of any untracked or modified files in the repo."""
        cmd = ['git', 'ls-files', '-mo', '--exclude-standard']
        p = self.run(cmd, stdout=subprocess.PIPE)
        return p.stdout.splitlines()

    @property
    def HEAD(self):
        """Return the commit hash for git HEAD."""
        p = self.run(['git', 'rev-parse', '--short', 'HEAD'], stdout=subprocess.PIPE)
        return p.stdout.strip()

    def __str__(self):
        return self.path

    def commit(self, msg, signoff=False):
        """Make a commit to the repo."""
        if isinstance(msg, str):
            msg = msg.splitlines()
        if signoff:
            msg.extend(['', 'Signed-off-by: First Last <first.last@email.com>'])
        self.run(['git', 'commit', '-m', '\n'.join(msg)])

    def add(self, file_path, msg='commit', commit=True, create=False, signoff=False):
        """Add a file and commit it to the repo."""
        if create:
            touch(pjoin(self.path, file_path))
        self.run(['git', 'add', file_path])
        if commit:
            self.commit(msg, signoff)

    def add_all(self, msg='commit-all', commit=True, signoff=False):
        """Add and commit all tracked and untracked files."""
        self.run(['git', 'add', '--all'])
        if commit:
            self.commit(msg, signoff)

    def remove(self, path, msg='remove', commit=True, signoff=False):
        """Remove a given file path and commit the change."""
        self.run(['git', 'rm', path])
        if commit:
            self.commit(msg, signoff)

    def remove_all(self, path, msg='remove-all', commit=True, signoff=False):
        """Remove all files from a given path and commit the changes."""
        self.run(['git', 'rm', '-rf', path])
        if commit:
            self.commit(msg, signoff)

    def move(self, path, new_path, msg=None, commit=True, signoff=False):
        """Move a given file path and commit the change."""
        msg = msg if msg is not None else f'{path} -> {new_path}'
        self.run(['git', 'mv', path, new_path])
        if commit:
            self.commit(msg, signoff)


@pytest.fixture
def git_repo(tmp_path_factory):
    """Create an empty git repo with an initial commit."""
    return GitRepo(str(tmp_path_factory.mktemp('git-repo')), commit=True)


@pytest.fixture
def make_git_repo(tmp_path_factory):
    """Factory for git repo creation."""
    def _make_git_repo(path=None, **kwargs):
        path = str(tmp_path_factory.mktemp('git-repo')) if path is None else path
        return GitRepo(path, **kwargs)
    return _make_git_repo


class _FileSet(MutableSet):
    """Set object that maps to file content updates for a given path."""

    def __init__(self, path):
        self._path = path
        self._set = set()

    def _sync(self):
        with open(self._path, 'w') as f:
            f.write('\n'.join(self._set) + '\n')

    def __contains__(self, key):
        return key in self._set

    def __iter__(self):
        return iter(self._set)

    def __len__(self):
        return len(self._set)

    def update(self, iterable):
        orig_entries = len(self._set)
        self._set.update(iterable)
        if len(self._set) != orig_entries:
            self._sync()

    def add(self, value):
        orig_entries = len(self._set)
        self._set.add(value)
        if len(self._set) != orig_entries:
            self._sync()

    def remove(self, value):
        orig_entries = len(self._set)
        self._set.remove(value)
        if len(self._set) != orig_entries:
            self._sync()

    def discard(self, value):
        orig_entries = len(self._set)
        self._set.discard(value)
        if len(self._set) != orig_entries:
            self._sync()


class EbuildRepo:
    """Class for creating/manipulating ebuild repos."""

    def __init__(self, path, repo_id='fake', eapi='5', masters=(), arches=()):
        self.path = path
        self.arches = _FileSet(pjoin(self.path, 'profiles', 'arch.list'))
        self._today = datetime.today()
        try:
            os.makedirs(pjoin(path, 'profiles'))
            with open(pjoin(path, 'profiles', 'repo_name'), 'w') as f:
                f.write(f'{repo_id}\n')
            with open(pjoin(path, 'profiles', 'eapi'), 'w') as f:
                f.write(f'{eapi}\n')
            os.makedirs(pjoin(path, 'metadata'))
            with open(pjoin(path, 'metadata', 'layout.conf'), 'w') as f:
                f.write(textwrap.dedent(f"""\
                    masters = {' '.join(masters)}
                    cache-formats =
                    thin-manifests = true
                """))
            if arches:
                self.arches.update(arches)
            os.makedirs(pjoin(path, 'eclass'))
        except FileExistsError:
            pass
        self.sync()

    def sync(self):
        """Forcibly create underlying repo object avoiding cache usage."""
        # avoid issues loading modules that set signal handlers
        from pkgcore.ebuild import repo_objs, repository
        repo_config = repo_objs.RepoConfig(location=self.path, disable_inst_caching=True)
        self._repo = repository.UnconfiguredTree(self.path, repo_config=repo_config)

    def create_profiles(self, profiles):
        for p in profiles:
            os.makedirs(pjoin(self.path, 'profiles', p.path), exist_ok=True)
            with open(pjoin(self.path, 'profiles', 'profiles.desc'), 'a+') as f:
                f.write(f'{p.arch} {p.path} {p.status}\n')
            if p.deprecated:
                with open(pjoin(self.path, 'profiles', p.path, 'deprecated'), 'w') as f:
                    f.write("# deprecated\ndeprecation reason\n")
            with open(pjoin(self.path, 'profiles', p.path, 'make.defaults'), 'w') as f:
                if p.defaults is not None:
                    f.write('\n'.join(p.defaults))
                else:
                    f.write(f'ARCH={p.arch}\n')
            if p.eapi:
                with open(pjoin(self.path, 'profiles', p.path, 'eapi'), 'w') as f:
                    f.write(f'{p.eapi}\n')

    def create_ebuild(self, cpvstr, data=None, **kwargs):
        from pkgcore.ebuild import cpv as cpv_mod
        cpv = cpv_mod.VersionedCPV(cpvstr)
        self._repo.notify_add_package(cpv)
        ebuild_dir = pjoin(self.path, cpv.category, cpv.package)
        os.makedirs(ebuild_dir, exist_ok=True)

        # use defaults for some ebuild metadata if unset
        eapi = kwargs.pop('eapi', '7')
        slot = kwargs.pop('slot', '0')
        desc = kwargs.pop('description', 'stub package description')
        homepage = kwargs.pop('homepage', 'https://github.com/pkgcore/pkgcheck')
        license = kwargs.pop('license', 'blank')

        ebuild_path = pjoin(ebuild_dir, f'{cpv.package}-{cpv.fullver}.ebuild')
        with open(ebuild_path, 'w') as f:
            if self.repo_id == 'gentoo':
                f.write(textwrap.dedent(f"""\
                    # Copyright 1999-{self._today.year} Gentoo Authors
                    # Distributed under the terms of the GNU General Public License v2
                """))
            f.write(f'EAPI="{eapi}"\n')
            f.write(f'DESCRIPTION="{desc}"\n')
            f.write(f'HOMEPAGE="{homepage}"\n')
            f.write(f'SLOT="{slot}"\n')

            if license:
                f.write(f'LICENSE="{license}"\n')
                # create a fake license
                os.makedirs(pjoin(self.path, 'licenses'), exist_ok=True)
                touch(pjoin(self.path, 'licenses', license))

            for k, v in kwargs.items():
                # handle sequences such as KEYWORDS and IUSE
                if isinstance(v, (tuple, list)):
                    v = ' '.join(v)
                f.write(f'{k.upper()}="{v}"\n')
            if data:
                f.write(data.strip() + '\n')

        return ebuild_path

    def __iter__(self):
        yield from iter(self._repo)

    __getattr__ = klass.GetAttrProxy('_repo')
    __dir__ = klass.DirProxy('_repo')


@pytest.fixture
def repo(tmp_path_factory):
    """Create a generic ebuild repository."""
    return EbuildRepo(str(tmp_path_factory.mktemp('repo')))


@pytest.fixture
def make_repo(tmp_path_factory):
    """Factory for ebuild repo creation."""
    def _make_repo(path=None, **kwargs):
        path = str(tmp_path_factory.mktemp('repo')) if path is None else path
        return EbuildRepo(path, **kwargs)
    return _make_repo
