# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, darcs
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(darcs.darcs_syncer)
valid = make_valid_syncer(darcs.darcs_syncer)


class TestDarcsSyncer(object):

    def test_uri_parse(self):
        assert darcs.darcs_syncer.parse_uri("darcs+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            darcs.darcs_syncer.parse_uri("darcs://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "darcs+http://foon.com/dar")

        o = valid("/tmp/foon", "darcs+http://dar")
        assert o.uri == "http://dar"
