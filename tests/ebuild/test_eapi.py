# Copyright: 2018 Tim Harder <radhermit@gmail.com>
# License: GPL2/BSD

from pkgcore.ebuild.eapi import (
    EAPI, eapi0, eapi1, eapi2, eapi3, eapi4, eapi5, eapi6, eapi7)

import pytest


class TestEAPI(object):

    def test_register_known(self):
        # re-register known EAPI
        with pytest.raises(ValueError):
            EAPI.register(magic="0")

    def test_inherits(self):
        assert list(eapi0.inherits) == [eapi0]
        assert list(eapi7.inherits) == [eapi7, eapi6, eapi5, eapi4, eapi3, eapi2, eapi1, eapi0]
