# -*- coding: utf-8 -*-
# Copyright: 2015 Michał Górny <mgorny@gentoo.org>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, git_svn
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(git_svn.git_svn_syncer)
valid = make_valid_syncer(git_svn.git_svn_syncer)


class TestGitSVNSyncer(object):

    def test_uri_parse(self):
        assert git_svn.git_svn_syncer.parse_uri("git+svn+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            git_svn.git_svn_syncer.parse_uri("git+svn+://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "git+svn+http://foon.com/dar")

        o = valid("/tmp/foon", "git+svn+http://dar")
        assert o.uri == "http://dar"
