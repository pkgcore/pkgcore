"""tests for pkgcore.config's package __init__.py"""

import operator

from snakeoil.test import TestCase
from snakeoil.test.mixins import mk_named_tempfile

from pkgcore.config import basics, load_config
from pkgcore.config.hint import configurable


@configurable(typename='foo')
def passthrough(*args, **kwargs):
    return args, kwargs


class ConfigLoadingTest(TestCase):

    def setUp(self):
        self.user_config = mk_named_tempfile()
        self.user_config.write(
            '[foo]\n'
            'class = module.config.test_init.passthrough\n'
            )
        self.user_config.flush()
        self.system_config = mk_named_tempfile()
        self.system_config.write(
            '[foo]\n'
            'class = also invalid\n'
            )
        self.system_config.flush()

    def tearDown(self):
        self.user_config.close()
        self.system_config.close()
        del self.user_config
        del self.system_config

    def test_load_config(self):
        manager = load_config(user_conf_file=self.user_config.name)
        self.assertEqual(manager.foo['foo'], ((), {}))

        # Test user config overrides system config.
        manager = load_config(
            user_conf_file=self.user_config.name,
            system_conf_file=self.system_config.name)
        self.assertEqual(manager.foo['foo'], ((), {}))

        # Test prepends.
        manager = load_config(
            user_conf_file=self.user_config.name,
            prepend_sources=[{'myfoo': basics.HardCodedConfigSection({
                            'inherit': ['foo']})}])
        self.assertEqual(manager.foo['myfoo'], ((), {}))

        # Test disabling loading.
        manager = load_config(
            user_conf_file=self.user_config.name,
            skip_config_files=True)
        self.assertRaises(
            KeyError,
            operator.getitem, manager.foo, 'foo')
