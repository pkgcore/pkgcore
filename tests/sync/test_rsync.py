# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import datetime
import os
from unittest import mock

import pytest

from pkgcore.sync import base, rsync
from pkgcore.sync.tar import tar_syncer
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(rsync.rsync_syncer)
valid = make_valid_syncer(rsync.rsync_syncer)


class TestRsyncSyncer(object):

    def test_uri_parse(self):
        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "rsync+hopefully_nonexistent_binary://foon.com/dar")

        o = valid("/tmp/foon", "rsync://dar/module")
        assert o.rsh == None
        assert o.uri == "rsync://dar/module/"

        o = valid("/tmp/foon", "rsync+/bin/sh://dar/module")
        assert o.uri == "rsync://dar/module/"
        assert o.rsh == "/bin/sh"

    @mock.patch('snakeoil.process.find_binary', return_value='rsync')
    @mock.patch('snakeoil.process.spawn.spawn')
    def test_sync(self, spawn, find_binary, tmp_path):
        path = tmp_path / 'repo'
        syncer = rsync.rsync_syncer(
            str(path), "rsync://rsync.gentoo.org/gentoo-portage")

        # successful sync
        spawn.return_value = 0
        assert syncer.sync()
        spawn.assert_called_once()
        spawn.reset_mock()

        # failed sync
        spawn.return_value = 1
        with pytest.raises(base.SyncError):
            assert syncer.sync()
        spawn.assert_called_once()
        spawn.reset_mock()

        # retried sync
        spawn.return_value = 99
        with pytest.raises(base.SyncError):
            assert syncer.sync()
        # rsync should retry every resolved IP related to the sync URI
        assert len(spawn.mock_calls) > 1


@pytest.mark_network
class TestRsyncSyncerReal(object):

    def test_sync(self, tmp_path):
        # perform a tarball sync for initial week-old base
        path = tmp_path / 'repo'
        week_old = datetime.datetime.now() - datetime.timedelta(days=7)
        date_str = week_old.strftime("%Y%m%d")
        syncer = tar_syncer(
            str(path), f"http://distfiles.gentoo.org/snapshots/portage-{date_str}.tar.xz")
        assert syncer.sync()
        timestamp = os.path.join(path, 'metadata', 'timestamp.chk')
        assert os.path.exists(timestamp)
        stat = os.stat(timestamp)

        # run rsync over the unpacked repo tarball to update to the latest tree
        syncer = rsync.rsync_timestamp_syncer(
            str(path), "rsync://rsync.gentoo.org/gentoo-portage")
        assert syncer.sync()
        assert stat != os.stat(timestamp)
