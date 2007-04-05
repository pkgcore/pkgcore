# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.test.sync import make_bogus_syncer, make_valid_syncer
from pkgcore.sync import base, rsync

bogus = make_bogus_syncer(rsync.rsync_syncer)
valid = make_valid_syncer(rsync.rsync_syncer)

class TestrsyncParsing(TestCase):

    def test_parse(self):
        self.assertRaises(base.syncer_exception, bogus,
            "/tmp/foon", "rsync+hopefully_nonexistant_binary://foon.com/dar")
        o = valid("/tmp/foon", "rsync://dar/module")
        self.assertEqual(o.rsh, None)
        self.assertEqual(o.uri, "rsync://dar/module/")

        o = valid("/tmp/foon", "rsync+/bin/sh://dar/module")
        self.assertEqual(o.uri, "rsync://dar/module/")
        self.assertEqual(o.rsh, "/bin/sh")
