# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""tests for pkgcore.config's package __init__.py"""


import operator
import tempfile

from pkgcore.test import TestCase

from pkgcore.config import load_config, configurable, basics


@configurable(typename='foo')
def passthrough(*args, **kwargs):
    return args, kwargs


class ConfigLoadingTest(TestCase):

    def setUp(self):
        self.user_config = tempfile.NamedTemporaryFile()
        self.user_config.write(
            '[foo]\n'
            'class = pkgcore.test.config.test_init.passthrough\n'
            )
        self.user_config.flush()
        self.system_config = tempfile.NamedTemporaryFile()
        self.system_config.write(
            '[foo]\n'
            'class = also invalid\n'
            )
        self.system_config.flush()

    def tearDown(self):
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
