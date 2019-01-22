# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import pytest

from pkgcore.sync import base, cvs
from tests.sync.syncer import make_bogus_syncer, make_valid_syncer

bogus = make_bogus_syncer(cvs.cvs_syncer)
valid = make_valid_syncer(cvs.cvs_syncer)


class TestCVSSyncer(object):

    def test_uri_parse(self):
        with pytest.raises(base.SyncError):
            bogus("/tmp/foon", "cvs+hopefully_nonexistent_binary://foon.com/dar")

        o = valid("/tmp/foon", "cvs://dar:module")
        assert o.uri == ":anoncvs:dar"
        assert o.module == "module"
        assert o.rsh == None
        assert o.env["CVSROOT"] == ":anoncvs:dar"

        o = valid("/tmp/foon", "cvs+pserver://dar:module")
        assert o.uri == ":pserver:dar"
        assert o.module == "module"
        assert o.rsh == None
        assert o.env["CVSROOT"] == ":pserver:dar"

        o = valid("/tmp/foon", "cvs+/bin/sh://dar:module")
        assert o.rsh == "/bin/sh"
        assert o.uri == ":ext:dar"
        assert o.env["CVSROOT"] == ":ext:dar"
        assert o.env["CVS_RSH"] == "/bin/sh"
