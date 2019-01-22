# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
import pwd

import pytest

from pkgcore.sync import base, git, tar
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

valid = make_valid_syncer(base.ExternalSyncer)
bogus = make_bogus_syncer(base.ExternalSyncer)

existing_user = pwd.getpwall()[0].pw_name
existing_uid = pwd.getpwnam(existing_user).pw_uid


class TestSyncer(object):

    def test_split_users(self):
        o = base.Syncer("/tmp/foon", "http://dar")
        assert o.uid == os.getuid()
        assert o.uri == "http://dar"

        o = base.Syncer("/tmp/foon", f"http://{existing_user}::@site")
        assert o.uid == existing_uid
        assert o.uri == "http://site"

        o = base.Syncer("/tmp/foon", f"http://{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "http://foon@site"

        o = base.Syncer("/tmp/foon", f"{existing_user}::foon@site")
        assert o.uid == existing_uid
        assert o.uri == "foon@site"


class TestExternalSyncer(object):

    def test_missing_binary(self):
        with pytest.raises(base.MissingBinary):
            bogus("/tmp/foon", "http://dar")

    def test_existing_binary(self):
        o = valid("/tmp/foon", "http://dar")
        assert o.uri == "http://dar"
        assert o.binary == "/bin/sh"


class TestGenericSyncer(object):

    def test_init(self):
        with pytest.raises(base.UriError):
            base.GenericSyncer('/', 'seriouslynotaprotocol://blah/')

        syncer = base.GenericSyncer('/', f'tar+https://blah.tar.gz')
        assert tar.tar_syncer is syncer.__class__


class TestDisabledSyncer(object):

    def test_init(self):
        syncer = base.DisabledSyncer('/foo/bar', f'https://blah.git')
        assert syncer.disabled
        # syncing should also be disabled
        assert not syncer.uri
        assert not syncer.sync()


class TestAutodetectSyncer(object):

    def test_no_syncer_detected(self, tmp_path):
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, base.DisabledSyncer)

    def test_syncer_detected(self, tmp_path):
        d = tmp_path / ".git"
        d.mkdir()
        syncer = base.AutodetectSyncer(str(tmp_path))
        assert isinstance(syncer, git.git_syncer)
