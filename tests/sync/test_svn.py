# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, svn
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(svn.svn_syncer)
valid = make_valid_syncer(svn.svn_syncer)


class TestSVNSyncer(object):

    def test_uri_parse(self):
        with pytest.raises(base.UriError):
            svn.svn_syncer.parse_uri("svn+://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "svn+http://foon.com/dar")

        o = valid("/tmp/foon", "svn+http://dar")
        assert o.uri == "http://dar"
