# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
from unittest import mock

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

    @mock.patch('snakeoil.process.find_binary', return_value='git')
    @mock.patch('snakeoil.process.spawn.spawn')
    def test_sync(self, spawn, find_binary, tmp_path):
        path = tmp_path / 'repo'
        uri = 'git://foo.git'

        syncer = git.git_syncer(str(path), uri)
        # initial sync
        syncer.sync()
        assert spawn.call_args[0] == (['git', 'clone', uri, str(path) + os.path.sep],)
        assert spawn.call_args[1]['cwd'] is None
        # repo update
        path.mkdir()
        syncer.sync()
        assert spawn.call_args[0] == (['git', 'pull'],)
        assert spawn.call_args[1]['cwd'] == syncer.basedir


@pytest.mark_network
class TestGitSyncerReal(object):

    def test_sync(self, tmp_path):
        path = tmp_path / 'repo'
        syncer = git.git_syncer(str(path), "https://github.com/pkgcore/pkgrepo.git")
        assert syncer.sync()
        assert os.path.exists(os.path.join(path, 'metadata', 'layout.conf'))
        assert syncer.sync()
