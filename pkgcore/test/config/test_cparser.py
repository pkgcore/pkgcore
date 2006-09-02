# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from StringIO import StringIO

from twisted.trial import unittest

from pkgcore.config import cparser, central, errors


class CaseSensitiveConfigParserTest(unittest.TestCase):

	def test_case_sensitivity(self):
		cp = cparser.CaseSensitiveConfigParser()
		cp.readfp(StringIO('\n'.join((
						'[header]',
						'foo=bar',
						'FOO=BAR',
						'[HEADER]',
						'foo=notbar',
						))))
		self.assertEquals(cp.get('header', 'foo'), 'bar')
		self.assertEquals(cp.get('header', 'FOO'), 'BAR')
		self.assertEquals(cp.get('HEADER', 'foo'), 'notbar')


class TypesConfigFromIniTest(unittest.TestCase):

	def test_basic(self):
		types = cparser.configTypesFromIni(StringIO("""
# random comment

[profile]
list = %(stuff)s extra
incrementals = %(stuff)s
class = pkgcore.ebuild blah
defaults = class

[DEFAULT]
stuff = basic

"""))
		self.assertEquals(types.keys(), ['profile'])
		self.assertEquals(types['profile'].incrementals, ('basic',))
		self.assertEquals(types['profile'].positional, ())
		self.assertEquals(types['profile'].required, ())
		self.assertEquals(
			types['profile'].types,
			{'basic': 'list',
			 'extra': 'list',
			 'class': 'callable',
			 'inherit': 'list',
			 'type': 'str',
			 })
		self.assertEquals(types['profile'].defaults.keys(), ['class'])

	def test_defaults(self):
		types = cparser.configTypesFromIni(StringIO('''
[test]
defaults = foo
foo = bar
'''))
		testtype = types['test']
		self.assertEquals(types['test'].incrementals, ())
		self.assertEquals(types['test'].positional, ())
		self.assertEquals(types['test'].required, ())
		self.assertEquals(testtype.defaults.keys(), ['foo'])

	def test_missing_defaults(self):
		types = StringIO('''
[test]
defaults = foo
''')
		self.assertRaises(
			errors.TypeDefinitionError,
			cparser.configTypesFromIni, types)

	def test_leftover_defaults(self):
		types = StringIO('''
[test]
defaults = foo
foo = bar
bar = baz
''')
		self.assertRaises(
			errors.TypeDefinitionError,
			cparser.configTypesFromIni, types)

	def test_duplicate_type(self):
		types = StringIO('''
[test]
str = foo
list = foo
''')
		self.assertRaises(
			errors.TypeDefinitionError,
			cparser.configTypesFromIni, types)


class ConfigFromIniTest(unittest.TestCase):

	def test_config_from_ini(self):
		config = cparser.configFromIni(StringIO('''
[test]
string = 'hi I am a string'
list = foo bar baz
true = yes
false = no
'''))
		self.assertEquals(config.keys(), ['test'])
		section = config['test']
		for key, arg_type, value in [
			('string', 'str', 'hi I am a string'),
			('list', 'list', ['foo', 'bar', 'baz']),
			('true', 'bool', True),
			('false', 'bool', False),
			]:
			self.assertEquals(section.get_value(None, key, arg_type), value)

	def test_missing_section_ref(self):
		config = cparser.configFromIni(StringIO('''
[test]
ref = 'missing'
'''))
		section = config['test']
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value,
			central.ConfigManager([], []), 'ref', 'section_ref')
