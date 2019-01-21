# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, git
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(git.git_syncer)
valid = make_valid_syncer(git.git_syncer)


class TestGitSyncer(object):

    def test_uri_parse(self):
        assert git.git_syncer.parse_uri("git+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            git.git_syncer.parse_uri("git+://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "git+http://foon.com/dar")

        for proto in ('http', 'https'):
            for uri in (f"git+{proto}://repo.git", f"{proto}://repo.git"):
                o = valid("/tmp/foon", uri)
                assert o.uri == f"{proto}://repo.git"
