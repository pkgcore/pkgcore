# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""tests for pkgcore.config's package __init__.py"""


import tempfile

from twisted.trial import unittest

from pkgcore.config import load_config, errors


def passthrough(*args, **kwargs):
	return args, kwargs


class ConfigLoadingTest(unittest.TestCase):

	def setUp(self):
		self.types = tempfile.NamedTemporaryFile()
		self.types.write(
			'[foo]\n'
			)
		self.types.flush()
		self.localConfig = tempfile.NamedTemporaryFile()
		self.localConfig.write(
			'[foo]\n'
			'type = foo\n'
			'class = pkgcore.test.config.test_init.passthrough\n'
			)
		self.localConfig.flush()
		self.globalConfig = tempfile.NamedTemporaryFile()
		self.globalConfig.write(
			'[foo]\n'
			'type = foo\n'
			'class = invalid\n'
			)
		self.globalConfig.flush()

	def tearDown(self):
		del self.types
		del self.localConfig
		del self.globalConfig

	def test_load_config(self):
		manager = load_config(
			self.localConfig.name, self.globalConfig.name, self.types.name)
		self.assertEquals(manager.foo['foo'], ((), {}))
