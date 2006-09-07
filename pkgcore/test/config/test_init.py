# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""tests for pkgcore.config's package __init__.py"""


import tempfile

from twisted.trial import unittest

from pkgcore.config import load_config


def passthrough(*args, **kwargs):
    return args, kwargs


class ConfigLoadingTest(unittest.TestCase):

    def setUp(self):
        self.types = tempfile.NamedTemporaryFile()
        self.types.write(
            '[foo]\n'
            )
        self.types.flush()
        self.user_config = tempfile.NamedTemporaryFile()
        self.user_config.write(
            '[foo]\n'
            'type = foo\n'
            'class = pkgcore.test.config.test_init.passthrough\n'
            )
        self.user_config.flush()
        self.global_config = tempfile.NamedTemporaryFile()
        self.global_config.write(
            '[foo]\n'
            'type = foo\n'
            'class = invalid\n'
            )
        self.global_config.flush()
        self.system_config = tempfile.NamedTemporaryFile()
        self.system_config.write(
            '[foo]\n'
            'type = foo\n'
            'class = also invalid\n'
            )
        self.system_config.flush()

    def tearDown(self):
        del self.types
        del self.user_config
        del self.global_config
        del self.system_config

    def test_load_config(self):
        manager = load_config(
            user_conf_file=self.user_config.name,
            global_conf_file=self.global_config.name,
            types_file=self.types.name)
        self.assertEquals(manager.foo['foo'], ((), {}))

    def test_stacking(self):
        """Test user config overrides system config."""
        manager = load_config(
            user_conf_file=self.user_config.name,
            system_conf_file=self.system_config.name,
            global_conf_file=self.global_config.name,
            types_file=self.types.name)
        self.assertEquals(manager.foo['foo'], ((), {}))
