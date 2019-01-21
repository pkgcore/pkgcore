# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
import pwd

import pytest

from pkgcore.sync import base, git
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

valid = make_valid_syncer(base.ExternalSyncer)
bogus = make_bogus_syncer(base.ExternalSyncer)

existing_user = pwd.getpwall()[0].pw_name
existing_uid = pwd.getpwnam(existing_user).pw_uid


class TestExternalSyncer(object):

    def test_init(self):
        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "http://dar")

        o = valid("/tmp/foon", "http://dar")
        assert o.local_user == os.getuid()
        assert o.uri == "http://dar"

        o = valid("/tmp/foon", f"http://{existing_user}::@site")
        assert o.local_user == existing_uid
        assert o.uri == "http://site"

        o = valid("/tmp/foon", f"http://{existing_user}::foon@site")
        assert o.local_user == existing_uid
        assert o.uri == "http://foon@site"

        o = valid("/tmp/foon", f"{existing_user}::foon@site")
        assert o.local_user == existing_uid
        assert o.uri == "foon@site"


class TestGenericSyncer(object):

    def test_init(self):
        with pytest.raises(base.UriError):
            base.GenericSyncer('/', 'seriouslynotaprotocol://blah/')

        # TODO: switch to tarball syncer once support is implemented
        syncer = base.GenericSyncer('/', f'git://blah/')
        assert git.git_syncer is syncer.__class__
