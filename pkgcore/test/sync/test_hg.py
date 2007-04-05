# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.test import TestCase
from pkgcore.test.sync import make_bogus_syncer, make_valid_syncer
from pkgcore.sync import base, hg

bogus = make_bogus_syncer(hg.hg_syncer)
valid = make_valid_syncer(hg.hg_syncer)

class TestHgParsing(TestCase):

    def test_parse(self):
        self.assertEqual(hg.hg_syncer.parse_uri("hg+http://dar"),
            "http://dar")
        self.assertRaises(base.uri_exception, hg.hg_syncer.parse_uri,
            "hg://dar")
        self.assertRaises(base.syncer_exception, bogus,
            "/tmp/foon", "hg+http://foon.com/dar")
        o = valid("/tmp/foon", "hg+http://dar")
        self.assertEqual(o.uri, "http://dar")
