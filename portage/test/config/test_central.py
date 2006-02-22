# Copyright: 2005 Gentoo Foundation
# License: GPL2


from twisted.trial import unittest

from portage.config import central, basics, errors


def passthrough(*args, **kwargs):
	return args, kwargs


# The exception checks here also check if the str value of the
# exception is what we expect. This does not mean the wording of the
# error messages used here is strictly required. It just makes sure
# the error we get is the expected one and is useful. Please make sure
# you check for a sensible error message when more tests are added.


class ConfigManagerTest(unittest.TestCase):

	def test_sections(self):
		manager = central.ConfigManager(
			[{'foo': basics.ConfigType('foo', {}),
			  'bar': basics.ConfigType('bar', {}),
			  }],
			[{'fooinst': basics.HardCodedConfigSection(
						'fooinst', {'type': 'foo', 'class': passthrough}),
			  'barinst': basics.HardCodedConfigSection(
						'barinst', {'type': 'bar', 'class': passthrough}),
			  }])
		self.assertEquals(sorted(manager.sections()), ['barinst', 'fooinst'])
		self.assertEquals(manager.sections('foo'), ['fooinst'])
		self.assertEquals(manager.bar, {'barinst': ((), {})})

	def test_duplicate_type(self):
		try:
			central.ConfigManager(
				[{'foo': basics.ConfigType('foo', {})},
				 {'foo': basics.ConfigType('foo2', {})}],
			[])
		except errors.BaseException, e:
			self.assertEquals("type 'foo' was defined twice", str(e))
		else:
			self.fail('no exception raised')

	def test_no_type(self):
		manager = central.ConfigManager(
			[],
			[{'foo': basics.HardCodedConfigSection(
						'foo', {'class': passthrough})}])
		try:
			manager.instantiate_section('foo')
		except errors.ConfigurationError, e:
			self.assertEquals('foo: type not set', str(e))
		else:
			self.fail('no exception raised')

	def test_no_class(self):
		manager = central.ConfigManager(
			[{'footype': basics.ConfigType('foo', {})}],
			[{'foo': basics.HardCodedConfigSection(
						'foo', {'type': 'footype'})}])
		try:
			manager.instantiate_section('foo')
		except errors.ConfigurationError, e:
			self.assertEquals('foo: no class specified', str(e))
		else:
			self.fail('no exception raised')

	def test_default_class(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {}, required=['class'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'rsync repo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							}),
			  }])
		self.failUnlessEquals(((), {}), manager.repo['rsync repo'])

	def test_missing_section_ref(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {'cache': 'section_ref'},
						required=['class', 'cache'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'rsync repo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': passthrough,
							}),
			  }])
		try:
			manager.repo['rsync repo']
		except errors.ConfigurationError, e:
			self.assertEquals(
				"type 'repo' needs a setting for 'cache' in section "
				"'rsync repo'", str(e))
		else:
			self.fail('no exception raised')

	def test_missing_inherit_target(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {}, required=['class', 'cache'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test2', {
							'type': 'repo',
							'inherit': ['baserepo'],
							}),
			  }])
		try:
			manager.repo['myrepo']
		except errors.ConfigurationError, e:
			self.failUnless(
				"inherit target 'baserepo' cannot be found" in str(e))
		else:
			self.fail('no exception raised')

	def test_inherit_unknown_type(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {}, required=['class', 'cache'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'baserepo': basics.HardCodedConfigSection('test', {
							'cache': 'available',
							}),
			  'actual repo': basics.HardCodedConfigSection('test2', {
							'type': 'repo',
							'inherit': ['baserepo'],
							}),
			  }])
		try:
			manager.repo['actual repo']
		except errors.ConfigurationError, e:
			self.assertEquals(
				"'actual repo': type of 'cache' inherited from 'baserepo' "
				"unknown", str(e))
		else:
			self.fail('no exception raised')

	def test_inherit(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {'cache': 'str'}, required=['class', 'cache'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'baserepo': basics.HardCodedConfigSection('test', {
							'cache': 'available',
							}),
			  'actual repo': basics.HardCodedConfigSection('test2', {
							'type': 'repo',
							'inherit': ['baserepo'],
							}),
			  }])

		self.assertEquals(
			manager.repo['actual repo'], ((), {'cache': 'available'}))

	def test_incremental(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {'inc': 'list'}, required=['inc'],
						incrementals=['inc'],
						defaults=basics.HardCodedConfigSection('test', {
								'class': passthrough,
								}))
			  }],
			[{'baserepo': basics.HardCodedConfigSection('test', {
							'inc': ['basic'],
							}),
			  'actual repo': basics.HardCodedConfigSection('test2', {
							'type': 'repo',
							'inherit': ['baserepo'],
							'inc': ['extended']
							}),
			  }])
		self.assertEquals(
			manager.repo['actual repo'], ((), {'inc': ['basic', 'extended']}))

	def test_no_object_returned(self):
		def noop():
			"""Do not do anything."""

		manager = central.ConfigManager(
			[{'repo': basics.ConfigType('repo', {}),
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': noop,
							}),
			  }])
		try:
			manager.repo['myrepo']
		except errors.BaseException, e:
			self.failUnless(str(e).startswith(
					"Caught exception 'No object returned' instantiating "
					"<function noop "), str(e))
		else:
			self.fail('no exception raised')

	def test_not_callable(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType('repo', {}),
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': None,
							}),
			  }])
		try:
			manager.repo['myrepo']
		except errors.BaseException, e:
			self.assertEquals(str(e), "test: None is not callable")
		else:
			self.fail('no exception raised')

	def test_raises_instantiationerror(self):
		def inst():
			raise errors.InstantiationError(None, [], {}, 'I raised')
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType('repo', {}),
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': inst,
							}),
			  }])
		try:
			manager.repo['myrepo']
		except errors.BaseException, e:
			self.assertEquals(
				str(e), "Caught exception 'I raised' instantiating None")
		else:
			self.fail('no exception raised')

	def test_raises(self):
		def inst():
			raise ValueError('I raised')
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType('repo', {}),
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': inst,
							}),
			  }])
		try:
			manager.repo['myrepo']
		except ValueError, e:
			self.assertEquals(str(e), "I raised")
		else:
			self.fail('no exception raised')

	def test_pargs(self):
		manager = central.ConfigManager(
			[{'repo': basics.ConfigType(
						'repo', {
							'p': 'str',
							'notp': 'str',
							},
						positional=['p'], required=['p'])
			  }],
			[{'myrepo': basics.HardCodedConfigSection('test', {
							'type': 'repo',
							'class': passthrough,
							'p': 'pos',
							'notp': 'notpos',
							}),
			  }])

		self.assertEquals(
			manager.repo['myrepo'], (('pos',), {'notp': 'notpos'}))
