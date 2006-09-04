# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from pkgcore.config import basics, errors


def passthrough(*args, **kwargs):
	return args, kwargs


class ConfigTypeTest(unittest.TestCase):

	def test_invalid_types(self):
		for var in ('class', 'type', 'inherit'):
			self.assertRaises(
				errors.TypeDefinitionError,
				basics.ConfigType, 'testtype', {var: 'str'})
		self.assertRaises(
			errors.TypeDefinitionError,
			basics.ConfigType, 'test', {}, positional=['foo'])


class ConfigSectionTest(unittest.TestCase):

	def test_basics(self):
		section = basics.ConfigSection()
		self.assertRaises(NotImplementedError, section.__contains__, 42)
		self.assertRaises(NotImplementedError, section.keys)
		self.assertRaises(
			NotImplementedError, section.get_value, None, 'a', 'str')


class ConfigSectionFromStringDictTest(unittest.TestCase):

	def setUp(self):
		self.source = {
			'str': 'pkgcore.test',
			'bool': 'yes',
			'list': '0 1 2',
			'callable': 'pkgcore.test.config.test_basics.passthrough',
			}
		self.destination = {
			'str': 'pkgcore.test',
			'bool': True,
			'list': ['0', '1', '2'],
			'callable': passthrough,
			}
		self.section = basics.ConfigSectionFromStringDict('test', self.source)

	def test_contains(self):
		self.failIf('foo' in self.section)
		self.failUnless('list' in self.section)

	def test_keys(self):
		self.assertEquals(
			sorted(self.section.keys()), ['bool', 'callable', 'list', 'str'])

	def test_get_value(self):
		# valid gets
		for typename, value in self.destination.iteritems():
			self.assertEquals(
				value, self.section.get_value(None, typename, typename))
		# invalid gets
		# not callable
		self.assertRaises(
			errors.ConfigurationError,
			self.section.get_value, None, 'str', 'callable')
		# not importable
		self.assertRaises(
			errors.ConfigurationError,
			self.section.get_value, None, 'bool', 'callable')

	def test_section_ref(self):
		section = basics.ConfigSectionFromStringDict(
			'test', {'goodref': 'target', 'badref': 'missing'})
		target_config = object()
		class TestCentral(object):
			def get_section_config(self, section):
				return {'target': target_config}[section]
			def instantiate_section(self, name, conf):
				return name, conf
		self.assertEquals(
			section.get_value(TestCentral(), 'goodref', 'section_ref'),
			('target', target_config))
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, TestCentral(), 'badref', 'section_ref')

	def test_section_refs(self):
		section = basics.ConfigSectionFromStringDict(
			'test', {'goodrefs': '1 2', 'badrefs': '2 3'})
		config1 = object()
		config2 = object()
		class TestCentral(object):
			def get_section_config(self, section):
				return {'1': config1, '2': config2}[section]
			def instantiate_section(self, name, conf):
				return name, conf
		self.assertEquals(
			section.get_value(TestCentral(), 'goodrefs', 'section_refs'),
			[('1', config1), ('2', config2)])
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, TestCentral(), 'badrefs', 'section_refs')


class HardCodedConfigSectionTest(unittest.TestCase):

	def setUp(self):
		self.source = {
			'str': 'pkgcore.test',
			'bool': True,
			'list': ['0', '1', '2'],
			'callable': passthrough,
			}
		self.section = basics.HardCodedConfigSection('test', self.source)

	def test_contains(self):
		self.failIf('foo' in self.section)
		self.failUnless('str' in self.section)

	def test_keys(self):
		self.assertEquals(
			sorted(self.section.keys()), ['bool', 'callable', 'list', 'str'])

	def test_get_value(self):
		# try all combinations
		for arg, value in self.source.iteritems():
			for typename in self.source:
				if arg == typename:
					self.assertEquals(
						value, self.section.get_value(None, arg, typename))
				else:
					self.assertRaises(
						errors.ConfigurationError,
						self.section.get_value, None, arg, typename)

	def test_section_ref(self):
		# should have positive assertions here
		section = basics.HardCodedConfigSection('test', {'ref': 42})
		self.assertRaises(AssertionError,
			section.get_value, None, 'ref', 'section_ref')

	def test_section_refs(self):
		section = basics.HardCodedConfigSection('test', {'refs': [1, 2]})
		self.assertRaises(AssertionError,
			section.get_value, None, 'refs', 'section_refs')


class ParsersTest(unittest.TestCase):

	def test_bool_parser(self):
		# abuse Identical to make sure we get actual bools, not some
		# weird object that happens to be True or False when converted
		# to a bool
		for string, output in [
			('True', True),
			('yes', True),
			('1', True),
			('False', False),
			('no', False),
			('0', False),
			]:
			self.assertIdentical(basics.bool_parser(string), output)

	def test_str_parser(self):
		for string, output in [
			('\t ', ''),
			(' foo ', 'foo'),
			(' " foo " ', ' foo '),
			('\t"', '"'),
			('\nfoo\t\n bar\t', 'foo   bar'),
			('"a"', 'a'),
			("'a'", "a"),
			("'a", "'a"),
			('"a', '"a'),
			]:
			self.assertEquals(basics.str_parser(string), output)

	def test_list_parser(self):
		for string, output in [
			('foo', ['foo']),
			('"f\'oo"  \'b"ar\'', ["f'oo", 'b"ar']),
			('', []),
			(' ', []),
			('\\"hi ', ['"hi']),
			('\'"hi\'', ['"hi']),
			('"\\"hi"', ['"hi']),
			]:
			self.assertEquals(basics.list_parser(string), output)
		for string in ['"', "'foo", 'ba"r', 'baz"']:
			self.assertRaises(
				errors.QuoteInterpretationError, basics.list_parser, string)
		# make sure this explodes instead of returning something
		# confusing so we explode much later
		self.assertRaises(TypeError, basics.list_parser, ['no', 'string'])
