# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, hg
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(hg.hg_syncer)
valid = make_valid_syncer(hg.hg_syncer)


class TestHgSyncer(object):

    def test_uri_parse(self):
        assert hg.hg_syncer.parse_uri("hg+http://dar") == "http://dar"
        assert hg.hg_syncer.parse_uri("mercurial+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            hg.hg_syncer.parse_uri("hg://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "hg+http://foon.com/dar")

        o = valid("/tmp/foon", "hg+http://dar")
        assert o.uri == "http://dar"
