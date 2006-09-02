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
		self.userConfig = tempfile.NamedTemporaryFile()
		self.userConfig.write(
			'[foo]\n'
			'type = foo\n'
			'class = pkgcore.test.config.test_init.passthrough\n'
			)
		self.userConfig.flush()
		self.globalConfig = tempfile.NamedTemporaryFile()
		self.globalConfig.write(
			'[foo]\n'
			'type = foo\n'
			'class = invalid\n'
			)
		self.globalConfig.flush()
		self.systemConfig = tempfile.NamedTemporaryFile()
		self.systemConfig.write(
			'[foo]\n'
			'type = foo\n'
			'class = also invalid\n'
			)
		self.systemConfig.flush()

	def tearDown(self):
		del self.types
		del self.userConfig
		del self.globalConfig
		del self.systemConfig

	def test_load_config(self):
		manager = load_config(
			user_conf_file=self.userConfig.name,
			global_conf_file=self.globalConfig.name,
			types_file=self.types.name)
		self.assertEquals(manager.foo['foo'], ((), {}))

	def test_stacking(self):
		"""Test user config overrides system config."""
		manager = load_config(
			user_conf_file=self.userConfig.name,
			system_conf_file=self.systemConfig.name,
			global_conf_file=self.globalConfig.name,
			types_file=self.types.name)
		self.assertEquals(manager.foo['foo'], ((), {}))
