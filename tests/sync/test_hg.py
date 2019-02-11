# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
from unittest import mock

import pytest

from pkgcore.sync import base, hg
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(hg.hg_syncer)
valid = make_valid_syncer(hg.hg_syncer)


class TestHgSyncer(object):

    def test_uri_parse(self):
        assert hg.hg_syncer.parse_uri("hg+http://dar") == "http://dar"
        assert hg.hg_syncer.parse_uri("mercurial+http://dar") == "http://dar"

        with pytest.raises(base.UriError):
            hg.hg_syncer.parse_uri("hg://dar")

        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "hg+http://foon.com/dar")

        o = valid("/tmp/foon", "hg+http://dar")
        assert o.uri == "http://dar"

    @mock.patch('snakeoil.process.find_binary', return_value='hg')
    @mock.patch('snakeoil.process.spawn.spawn')
    def test_sync(self, spawn, find_binary, tmp_path):
        path = tmp_path / 'repo'
        uri = 'https://foo/bar'

        syncer = hg.hg_syncer(str(path), f'hg+{uri}')
        # initial sync
        syncer.sync()
        assert spawn.call_args[0] == (['hg', 'clone', uri, str(path) + os.path.sep],)
        assert spawn.call_args[1]['cwd'] is None
        # repo update
        path.mkdir()
        syncer.sync()
        assert spawn.call_args[0] == (['hg', 'pull', '-u', uri],)
        assert spawn.call_args[1]['cwd'] == syncer.basedir
