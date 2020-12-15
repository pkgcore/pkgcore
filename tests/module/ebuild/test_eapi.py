from importlib import reload
from unittest import mock

import pytest

from pkgcore.ebuild import eapi
from pkgcore.ebuild.eapi import EAPI, eapi6, get_eapi


def test_get_eapi():
    # unknown EAPI
    unknown_eapi = get_eapi("unknown")
    assert unknown_eapi in EAPI.unknown_eapis.values()
    # check that unknown EAPI is now registered as an unknown
    assert unknown_eapi == get_eapi("unknown")

    # known EAPI
    eapi = get_eapi("6")
    assert eapi6 == eapi


class TestEAPI:

    def test_register(self):
        # re-register known EAPI
        with pytest.raises(ValueError):
            EAPI.register(magic="0")

        with mock.patch('pkgcore.ebuild.eapi.bash_version') as bash_version, \
                mock.patch.dict(eapi.EAPI.known_eapis):
            # inadequate bash version
            bash_version.return_value = '3.1'
            with pytest.raises(SystemExit) as excinfo:
                new_eapi = EAPI.register(magic='new', optionals={'bash_compat': '3.2'})
            assert "EAPI 'new' requires >=bash-3.2, system version: 3.1" == excinfo.value.args[0]

            # adequate system bash versions
            bash_version.return_value = '3.2'
            test_eapi = EAPI.register(magic='test', optionals={'bash_compat': '3.2'})
            assert test_eapi._magic == 'test'
            bash_version.return_value = '4.2'
            test_eapi = EAPI.register(magic='test1', optionals={'bash_compat': '4.1'})
            assert test_eapi._magic == 'test1'

    def test_is_supported(self, caplog):
        assert eapi6.is_supported

        with mock.patch.dict(eapi.EAPI.known_eapis):
            # partially supported EAPI is flagged as such
            test_eapi = EAPI.register("test", optionals={'is_supported': False})
            assert test_eapi.is_supported
            assert caplog.text.endswith("EAPI 'test' isn't fully supported\n")

            # unsupported/unknown EAPI is flagged as such
            unknown_eapi = get_eapi("blah")
            assert not unknown_eapi.is_supported

    def test_inherits(self):
        for eapi_str, eapi_obj in EAPI.known_eapis.items():
            objs = (get_eapi(str(x)) for x in range(int(eapi_str), -1, -1))
            assert list(map(str, eapi_obj.inherits)) == list(map(str, objs))

    def test_ebd_env(self):
        for eapi_str, eapi_obj in EAPI.known_eapis.items():
            assert eapi_obj.ebd_env['EAPI'] == eapi_str
