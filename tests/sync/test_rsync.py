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


def test_uri_parse():
    with pytest.raises(base.SyncError):
        bogus("/tmp/foon", "rsync+hopefully_nonexistent_binary://foon.com/dar")

    o = valid("/tmp/foon", "rsync://dar/module")
    assert o.rsh == None
    assert o.uri == "rsync://dar/module/"

    o = valid("/tmp/foon", "rsync+/bin/sh://dar/module")
    assert o.uri == "rsync://dar/module/"
    assert o.rsh == "/bin/sh"


def fake_ips(num):
    """Generate simple IPv4 addresses given the amount to create."""
    return [
        (None, None, None, None, ('.'.join(str(x) * 4), 0))
        for x in range(num)
    ]


@mock.patch('snakeoil.process.find_binary', return_value='rsync')
@mock.patch('socket.getaddrinfo', return_value=fake_ips(3))
@mock.patch('snakeoil.process.spawn.spawn')
class TestRsyncSyncer(object):

    _syncer_class = rsync.rsync_syncer

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        path = tmp_path / 'repo'
        self.syncer = self._syncer_class(
            str(path), "rsync://rsync.gentoo.org/gentoo-portage")

    def test_successful_sync(self, spawn, getaddrinfo, find_binary):
        spawn.return_value = 0
        assert self.syncer.sync()
        spawn.assert_called_once()

    def test_bad_syntax_sync(self, spawn, getaddrinfo, find_binary):
        spawn.return_value = 1
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value).startswith('rsync command syntax error:')
        spawn.assert_called_once()

    def test_failed_disk_space_sync(self, spawn, getaddrinfo, find_binary):
        spawn.return_value = 11
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == 'rsync ran out of disk space'
        spawn.assert_called_once()

    def test_retried_sync(self, spawn, getaddrinfo, find_binary):
        spawn.return_value = 99
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == 'all attempts failed'
        # rsync should retry every resolved IP related to the sync URI
        assert len(spawn.mock_calls) == 3

    def test_retried_sync_max_retries(self, spawn, getaddrinfo, find_binary):
        spawn.return_value = 99
        # generate more IPs than retries
        getaddrinfo.return_value = fake_ips(self.syncer.retries + 1)
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == 'all attempts failed'
        assert len(spawn.mock_calls) == self.syncer.retries

    def test_failed_dns_sync(self, spawn, getaddrinfo, find_binary):
        getaddrinfo.side_effect = OSError()
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value).startswith('DNS resolution failed')
        spawn.assert_not_called()


class TestRsyncTimestampSyncer(TestRsyncSyncer):

    _syncer_class = rsync.rsync_timestamp_syncer


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
