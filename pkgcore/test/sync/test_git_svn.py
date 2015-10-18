# -*- coding: utf-8 -*-
# Copyright: 2015 Michał Górny <mgorny@gentoo.org>
# License: GPL2/BSD

from pkgcore.sync import base, git_svn
from pkgcore.test import TestCase
from pkgcore.test.sync import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(git_svn.git_svn_syncer)
valid = make_valid_syncer(git_svn.git_svn_syncer)


class TestGitSVNSyncer(TestCase):

    def test_uri_parse(self):
        self.assertEqual(
            git_svn.git_svn_syncer.parse_uri("git+svn+http://dar"),
            "http://dar")
        self.assertRaises(
            base.uri_exception, git_svn.git_svn_syncer.parse_uri,
            "git+svn+://dar")
        self.assertRaises(
            base.syncer_exception, bogus,
            "/tmp/foon", "git+svn+http://foon.com/dar")
        o = valid("/tmp/foon", "git+svn+http://dar")
        self.assertEqual(o.uri, "http://dar")
