# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.test import TestCase
from pkgcore.test.sync import make_bogus_syncer, make_valid_syncer
from pkgcore.sync import base, bzr

bogus = make_bogus_syncer(bzr.bzr_syncer)
valid = make_valid_syncer(bzr.bzr_syncer)

class TestBzrParsing(TestCase):

    def test_parse(self):
        self.assertEqual(bzr.bzr_syncer.parse_uri("bzr+http://dar"),
            "http://dar")
        self.assertRaises(base.uri_exception, bzr.bzr_syncer.parse_uri,
            "bzr://dar")
        self.assertRaises(base.syncer_exception, bogus,
            "/tmp/foon", "bzr+http://foon.com/dar")
        o = valid("/tmp/foon", "bzr+http://dar")
        self.assertEqual(o.uri, "http://dar")
