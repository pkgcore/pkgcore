"""tests for pkgcore.config's package __init__.py"""

import pytest

from pkgcore.config import basics, load_config
from pkgcore.config.hint import configurable
from snakeoil.test.mixins import mk_named_tempfile


@configurable(typename='foo')
def passthrough(*args, **kwargs):
    return args, kwargs


class TestConfigLoading:

    @pytest.fixture
    def user_config(self):
        user_config = mk_named_tempfile()
        user_config.write(
            '[foo]\n'
            'class = tests.config.test_init.passthrough\n'
        )
        user_config.flush()
        yield user_config
        user_config.close()

    @pytest.fixture
    def system_config(self):
        system_config = mk_named_tempfile()
        system_config.write(
            '[foo]\n'
            'class = also invalid\n'
        )
        system_config.flush()
        yield system_config
        system_config.close()

    def test_load_config(self, user_config):
        manager = load_config(user_conf_file=user_config.name)
        assert manager.foo['foo'] == ((), {})

    def test_user_config_override_system(self, user_config, system_config):
        manager = load_config(
            user_conf_file=user_config.name,
            system_conf_file=system_config.name)
        assert manager.foo['foo'] == ((), {})

    def test_prepends(self, user_config):
        manager = load_config(
            user_conf_file=user_config.name,
            prepend_sources=[{'myfoo': basics.HardCodedConfigSection({
                            'inherit': ['foo']})}])
        assert manager.foo['myfoo'] == ((), {})

    def test_disabling_loading(self, user_config):
        manager = load_config(
            user_conf_file=user_config.name,
            skip_config_files=True)
        with pytest.raises(KeyError):
            manager.foo['foo']
