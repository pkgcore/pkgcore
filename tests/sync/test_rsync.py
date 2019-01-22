# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, rsync
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
