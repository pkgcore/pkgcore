# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, bzr
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(bzr.bzr_syncer)
valid = make_valid_syncer(bzr.bzr_syncer)


class TestBzrSyncer(object):

    def test_uri_parse(self):
        assert bzr.bzr_syncer.parse_uri("bzr+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            bzr.bzr_syncer.parse_uri("bzr://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "bzr+http://foon.com/dar")

        o = valid("/tmp/foon", "bzr+http://dar")
        o.uri == "http://dar"
