# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base, git
from pkgcore.test import TestCase
from pkgcore.test.sync import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(git.git_syncer)
valid = make_valid_syncer(git.git_syncer)


class TestGitSyncer(TestCase):

    def test_uri_parse(self):
        self.assertEqual(git.git_syncer.parse_uri("git+http://dar"),
            "http://dar")
        self.assertRaises(base.uri_exception, git.git_syncer.parse_uri,
            "git+://dar")
        self.assertRaises(base.uri_exception, git.git_syncer.parse_uri,
            "https://foo.com/repo.git")
        self.assertRaises(base.syncer_exception, bogus,
            "/tmp/foon", "git+http://foon.com/dar")
        o = valid("/tmp/foon", "git+http://dar")
        self.assertEqual(o.uri, "http://dar")
