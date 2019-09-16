from unittest import mock

import pytest
from snakeoil.process import CommandNotFound

from pkgcore.sync import base, cvs


class TestCVSSyncer:

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / 'repo'

    def test_uri_parse(self):
        # external binary doesn't exist
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.side_effect = CommandNotFound('cvs')
            with pytest.raises(base.SyncError):
                cvs.cvs_syncer(
                    str(self.repo_path), "cvs+/bin/sh://foon.com/dar")

        # fake that the external binary exists
        with mock.patch('snakeoil.process.find_binary') as find_binary:
            find_binary.return_value = 'cvs'

            # nonexistent rsh
            with mock.patch('pkgcore.sync.base.ExternalSyncer.require_binary') as require_binary:
                require_binary.side_effect = base.MissingBinary('', 'rsh')
                with pytest.raises(base.SyncError):
                    cvs.cvs_syncer(str(self.repo_path), "cvs+rsh://foon.com/dar")

            o = cvs.cvs_syncer(str(self.repo_path), "cvs://dar:module")
            assert o.uri == ":anoncvs:dar"
            assert o.module == "module"
            assert o.rsh == None
            assert o.env["CVSROOT"] == ":anoncvs:dar"

            o = cvs.cvs_syncer(str(self.repo_path), "cvs+pserver://dar:module")
            assert o.uri == ":pserver:dar"
            assert o.module == "module"
            assert o.rsh == None
            assert o.env["CVSROOT"] == ":pserver:dar"

            with mock.patch('pkgcore.sync.base.ExternalSyncer.require_binary') as require_binary:
                require_binary.return_value = '/bin/sh'
                o = cvs.cvs_syncer(str(self.repo_path), "cvs+/bin/sh://dar:module")
                assert o.rsh == "/bin/sh"
                assert o.uri == ":ext:dar"
                assert o.env["CVSROOT"] == ":ext:dar"
                assert o.env["CVS_RSH"] == "/bin/sh"
