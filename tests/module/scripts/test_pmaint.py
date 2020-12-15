from functools import partial
from io import BytesIO

from snakeoil.formatters import PlainTextFormatter
from snakeoil.mappings import AttrAccessible
from snakeoil.test import TestCase

from pkgcore.config import basics
from pkgcore.config.hint import ConfigHint, configurable
from pkgcore.ebuild.cpv import CPV
from pkgcore.operations.repo import install, operations, replace, uninstall
from pkgcore.repository import syncable, util
from pkgcore.scripts import pmaint
from pkgcore.sync import base
from pkgcore.test.scripts.helpers import ArgParseMixin

Options = AttrAccessible


class fake_operations(operations):

    def _cmd_implementation_install(self, pkg, observer):
        self.repo.installed.append(pkg)
        return derive_op('add_data', install, self.repo, pkg, observer)

    def _cmd_implementation_uninstall(self, pkg, observer):
        self.repo.uninstalled.append(pkg)
        return derive_op('remove_data', uninstall, self.repo, pkg, observer)

    def _cmd_implementation_replace(self, oldpkg, newpkg, observer):
        self.repo.replaced.append((oldpkg, newpkg))
        return derive_op(('add_data', 'remove_data'),
            replace, self.repo, oldpkg, newpkg, observer)


class fake_repo(util.SimpleTree):

    operations_kls = fake_operations

    def __init__(self, data, frozen=False, livefs=False, repo_id=None):
        self.installed = []
        self.replaced = []
        self.uninstalled = []
        util.SimpleTree.__init__(
            self, data, pkg_klass=partial(fake_pkg, self), repo_id=repo_id)
        self.livefs = livefs
        self.frozen = frozen


def make_repo_config(repo_data, livefs=False, frozen=False, repo_id=None):
    def repo():
        return fake_repo(repo_data, livefs=livefs, frozen=frozen, repo_id=repo_id)
    repo.pkgcore_config_type = ConfigHint(typename='repo')
    return basics.HardCodedConfigSection({'class':repo})


class FakeDomain:

    pkgcore_config_type = ConfigHint({'repos': 'refs:repo',
                                      'binpkg': 'refs:repo',
                                      'vdb': 'refs:repo'},
                                     typename='domain')

    def __init__(self, repos, binpkg, vdb):
        object.__init__(self)
        self.repos = repos
        self.source_repos_raw = util.RepositoryGroup(repos)
        self.installed_repos = util.RepositoryGroup(vdb)
        self.binary_repos_raw = util.RepositoryGroup(binpkg)
        self.vdb = vdb


def make_domain(repo=None, binpkg=None, vdb=None):
    if repo is None:
        repo = {}
    if binpkg is None:
        binpkg = {}
    if vdb is None:
        vdb = {}
    repos_config = make_repo_config(repo, repo_id='fake')
    binpkg_config = make_repo_config(binpkg, frozen=False, repo_id='fake_binpkg')
    vdb_config = make_repo_config(vdb, repo_id='fake_vdb')

    return basics.HardCodedConfigSection({
        'class': FakeDomain,
        'repos': [repos_config],
        'binpkg': [binpkg_config],
        'vdb': [vdb_config],
        'default': True,
        })


class FakeSyncer(base.Syncer):

    def __init__(self,  *args, **kwargs):
        self.succeed = kwargs.pop('succeed', True)
        super().__init__(*args, **kwargs)
        self.synced = False

    def _sync(self, verbosity, output_fd, **kwds):
        self.synced = True
        return self.succeed


class SyncableRepo(syncable.tree, util.SimpleTree):

    pkgcore_config_type = ConfigHint(typename='repo_config')

    def __init__(self, succeed=True):
        util.SimpleTree.__init__(self, {})
        syncer = FakeSyncer('/fake', 'fake', succeed=succeed)
        syncable.tree.__init__(self, syncer)


success_section = basics.HardCodedConfigSection({'class': SyncableRepo,
                                                 'succeed': True})
failure_section = basics.HardCodedConfigSection({'class': SyncableRepo,
                                                 'succeed': False})


class TestSync(TestCase, ArgParseMixin):

    _argparser = pmaint.sync

    def test_parser(self):
        values = self.parse(repo=success_section)
        self.assertEqual(['repo'], [x[0] for x in values.repos])
        values = self.parse('repo', repo=success_section)
        self.assertEqual(['repo'], [x[0] for x in values.repos])

    def test_sync(self):
        config = self.assertOut(
            [
                "*** syncing myrepo",
                "*** synced myrepo",
                ],
            myrepo=success_section)
        self.assertTrue(config.repo_config['myrepo']._syncer.synced)
        self.assertOut(
            [
                "*** syncing myrepo",
                "!!! failed syncing myrepo",
                ],
            myrepo=failure_section)
        self.assertOutAndErr(
            [
                "*** syncing goodrepo",
                "*** synced goodrepo",
                "*** syncing badrepo",
                "!!! failed syncing badrepo",
                "",
                "*** sync results:",
                "*** synced: goodrepo",
                "!!! failed: badrepo",
                ], [],
            'goodrepo', 'badrepo',
            goodrepo=success_section, badrepo=failure_section)


class fake_pkg(CPV):

    def __init__(self, repo, *a, **kw):
        CPV.__init__(self, *a, **kw)
        object.__setattr__(self, 'repo', repo)

def derive_op(name, op, *a, **kw):
    if isinstance(name, str):
        name = [name]
    name = ['finalize_data'] + list(name)
    class new_op(op):
        def f(*a, **kw):
            return True
        for x in name:
            locals()[x] = f
        del f, x

    return new_op(*a, **kw)


class TestCopy(TestCase, ArgParseMixin):

    _argparser = pmaint.copy

    def execute_main(self, *a, **kw):
        config = self.parse(*a, **kw)
        out = PlainTextFormatter(BytesIO())
        ret = config.main_func(config, out, out)
        return ret, config, out

    def test_normal_function(self):
        ret, config, out = self.execute_main(
            'fake_binpkg', '--source-repo', 'fake_vdb',
            '*',
            domain=make_domain(vdb={'sys-apps':{'portage':['2.1', '2.3']}}),
            )
        self.assertEqual(ret, 0, "expected non zero exit code")
        self.assertEqual(list(map(str, config.target_repo.installed)),
            ['sys-apps/portage-2.1', 'sys-apps/portage-2.3'])
        self.assertEqual(config.target_repo.uninstalled,
            config.target_repo.replaced,
            msg="uninstalled should be the same as replaced; empty")

        d = {'sys-apps':{'portage':['2.1', '2.2']}}
        ret, config, out = self.execute_main(
            'fake_binpkg', '--source-repo', 'fake_vdb',
            '=sys-apps/portage-2.1',
            domain=make_domain(binpkg=d, vdb=d),
            )
        self.assertEqual(ret, 0, "expected non zero exit code")
        self.assertEqual([list(map(str, x)) for x in config.target_repo.replaced],
            [['sys-apps/portage-2.1', 'sys-apps/portage-2.1']])
        self.assertEqual(config.target_repo.uninstalled,
            config.target_repo.installed,
            msg="installed should be the same as uninstalled; empty")

    def test_ignore_existing(self):
        ret, config, out = self.execute_main(
            'fake_binpkg', '--source-repo', 'fake_vdb',
            '*', '--ignore-existing',
            domain=make_domain(vdb={'sys-apps':{'portage':['2.1', '2.3']}}),
            )
        self.assertEqual(ret, 0, "expected non zero exit code")
        self.assertEqual(list(map(str, config.target_repo.installed)),
            ['sys-apps/portage-2.1', 'sys-apps/portage-2.3'])
        self.assertEqual(config.target_repo.uninstalled,
            config.target_repo.replaced,
            msg="uninstalled should be the same as replaced; empty")

        ret, config, out = self.execute_main(
            'fake_binpkg', '--source-repo', 'fake_vdb',
            '*', '--ignore-existing',
            domain=make_domain(
                binpkg={'sys-apps':{'portage':['2.1']}},
                vdb={'sys-apps':{'portage':['2.1', '2.3']}}),
            )
        self.assertEqual(ret, 0, "expected non zero exit code")
        self.assertEqual(list(map(str, config.target_repo.installed)),
            ['sys-apps/portage-2.3'])
        self.assertEqual(config.target_repo.uninstalled,
            config.target_repo.replaced,
            msg="uninstalled should be the same as replaced; empty")


class TestRegen(TestCase, ArgParseMixin):

    _argparser = pmaint.regen

    def test_parser(self):

        options = self.parse(
            'fake', '--threads', '2', domain=make_domain())
        self.assertTrue(isinstance(options.repos[0], util.SimpleTree))
        self.assertEqual(options.threads, 2)
