# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base, svn
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer
from snakeoil.test import TestCase

bogus = make_bogus_syncer(svn.svn_syncer)
valid = make_valid_syncer(svn.svn_syncer)


class TestSVNSyncer(TestCase):

    def test_uri_parse(self):
        self.assertRaises(base.UriError, svn.svn_syncer.parse_uri,
            "svn+://dar")
        self.assertRaises(base.SyncError, bogus,
            "/tmp/foon", "svn+http://foon.com/dar")
        o = valid("/tmp/foon", "svn+http://dar")
        self.assertEqual(o.uri, "svn+http://dar")
