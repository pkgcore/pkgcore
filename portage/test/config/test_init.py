# Copyright: 2005 Gentoo Foundation
# License: GPL2

"""tests for portage.config's package __init__.py"""


import tempfile

from twisted.trial import unittest

from portage.config import load_config, errors


def passthrough(*args, **kwargs):
	return args, kwargs


class ConfigLoadingTest(unittest.TestCase):

	def setUp(self):
		self.types = tempfile.NamedTemporaryFile()
		self.types.write(
			'[foo]\n'
			)
		self.types.flush()
		self.config = tempfile.NamedTemporaryFile()
		self.config.write(
			'[foo]\n'
			'type = foo\n'
			'class = portage.test.config.test_init.passthrough\n'
			)
		self.config.flush()

	def tearDown(self):
		del self.types
		del self.config

	def test_load_config(self):
		manager = load_config(self.config.name, self.types.name)
		self.assertEquals(manager.foo['foo'], ((), {}))
		self.assertRaises(errors.BaseException, load_config, 'invalid')
