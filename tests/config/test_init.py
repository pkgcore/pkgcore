"""tests for pkgcore.config's package __init__.py"""

import pytest

from pkgcore.config import basics, load_config
from pkgcore.config.hint import configurable


@configurable(typename='foo')
def passthrough(*args, **kwargs):
    return args, kwargs


class TestConfigLoading:

    @pytest.fixture
    def user_config(self, tmp_path):
        user_config = tmp_path / 'user.conf'
        user_config.write_text(
            '[foo]\n'
            'class = tests.config.test_init.passthrough\n'
        )
        return str(user_config)

    @pytest.fixture
    def system_config(self, tmp_path):
        system_config = tmp_path / 'system.conf'
        system_config.write_text(
            '[foo]\n'
            'class = also invalid\n'
        )
        return str(system_config)

    def test_load_config(self, user_config):
        manager = load_config(user_conf_file=user_config)
        assert manager.foo['foo'] == ((), {})

    def test_user_config_override_system(self, user_config, system_config):
        manager = load_config(
            user_conf_file=user_config,
            system_conf_file=system_config)
        assert manager.foo['foo'] == ((), {})

    def test_prepends(self, user_config):
        manager = load_config(
            user_conf_file=user_config,
            prepend_sources=[{'myfoo': basics.HardCodedConfigSection({
                            'inherit': ['foo']})}])
        assert manager.foo['myfoo'] == ((), {})

    def test_disabling_loading(self, user_config):
        manager = load_config(
            user_conf_file=user_config,
            skip_config_files=True)
        with pytest.raises(KeyError):
            manager.foo['foo']
