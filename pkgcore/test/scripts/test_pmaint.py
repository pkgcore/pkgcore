# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmaint
from pkgcore.test.scripts import helpers
from pkgcore.config import basics, ConfigHint
from pkgcore.repository import util, syncable
from pkgcore.sync import base


class FakeSyncer(base.syncer):

    def __init__(self,  *args, **kwargs):
        self.succeed = kwargs.pop('succeed', True)
        base.syncer.__init__(self, *args, **kwargs)
        self.synced = False

    def _sync(self, verbosity, output_fd, **kwds):
        self.synced = True
        return self.succeed


class SyncableRepo(syncable.tree_mixin, util.SimpleTree):

    pkgcore_config_type = ConfigHint(typename='repo')

    def __init__(self, succeed=True):
        util.SimpleTree.__init__(self, {})
        syncer = FakeSyncer('/fake', 'fake', succeed=succeed)
        syncable.tree_mixin.__init__(self, syncer)


success_section = basics.HardCodedConfigSection({'class': SyncableRepo,
                                                 'succeed': True})
failure_section = basics.HardCodedConfigSection({'class': SyncableRepo,
                                                 'succeed': False})


class SyncTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmaint.SyncOptionParser())
    main = staticmethod(pmaint.sync_main)

    def test_parser(self):
        self.assertError(
            "repo 'missing' doesn't exist:\nvalid repos ['repo']",
            'missing', repo=success_section)
        values = self.parse(repo=success_section)
        self.assertEquals(['repo'], values.repos)
        values = self.parse('repo', repo=success_section)
        self.assertEquals(['repo'], values.repos)

    def test_sync(self):
        config = self.assertOut(
            [
                "*** syncing 'myrepo'...",
                "*** synced 'myrepo'",
                ],
            myrepo=success_section)
        self.assertTrue(config.repo['myrepo']._sync.synced)
        self.assertOut(
            [
                "*** syncing 'myrepo'...",
                "*** failed syncing 'myrepo'",
                ],
            myrepo=failure_section)
        self.assertOutAndErr(
            [
                "*** syncing 'goodrepo'...",
                "*** synced 'goodrepo'",
                "*** syncing 'badrepo'...",
                "*** failed syncing 'badrepo'",
                "*** synced 'goodrepo'",
                ], [
                "!!! failed sync'ing 'badrepo'",
                ],
            'goodrepo', 'badrepo',
            goodrepo=success_section, badrepo=failure_section)
