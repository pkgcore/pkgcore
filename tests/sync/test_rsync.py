# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import datetime
import os

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


@pytest.mark_network
class TestRsyncSyncerReal(object):

    def test_sync(self, tmp_path):
        # perform a tarball sync for initial week-old base
        path = tmp_path / 'repo'
        now = datetime.datetime.now()
        week_old = now - datetime.timedelta(days=7)
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
