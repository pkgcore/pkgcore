# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from StringIO import StringIO

from twisted.trial import unittest

try:
	import pyparsing
except ImportError:
	skip_test = True
else:
	skip_test = False
	from pkgcore.config import dhcpformat

from pkgcore.config import central, basics, errors

def passthrough(*args, **kwargs):
	return args, kwargs


class DHCPConfigTest(unittest.TestCase):
	if skip_test:
		skip = "missing pyparsing module"

	def test_basics(self):
		config = dhcpformat.configFromFile(StringIO('''
test {
    hi there;
}
'''))
		self.assertEquals(config.keys(), ['test'])
		section = config['test']
		self.failUnless('hi' in section)
		self.assertEquals(section.keys(), ['hi'])
		self.assertEquals(section.get_value(None, 'hi', 'str'), 'there')

	def test_basic_types(self):
		config = dhcpformat.configFromFile(StringIO('''
test {
    list one two three;
	string hi;
	bool yes;
	callable pkgcore.test.config.test_dhcpformat.passthrough;
}
'''))
		section = config['test']
		for name, typename, value in (
			('list', 'list', ['one', 'two', 'three']),
			('string', 'str', 'hi'),
			('bool', 'bool', True),
			('callable', 'callable', passthrough),
			):
			self.assertEquals(section.get_value(None, name, typename), value)

	def test_section_ref(self):
		config = dhcpformat.configFromFile(StringIO('''
target {
    type testtype;
	class pkgcore.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    ref target;
	inline {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	};
}
'''))
		manager = central.ConfigManager(
			[{'testtype': basics.ConfigType('testtype',	{'hi': 'str'})}],
			[config])
		section = config['test']
		self.assertEquals(
			section.get_value(manager, 'ref', 'section_ref'),
			((), {'hi': 'there'}))
		self.assertEquals(
			section.get_value(manager, 'inline', 'section_ref'),
			((), {'hi': 'here'}))

	def test_multiple_section_ref(self):
		config = dhcpformat.configFromFile(StringIO('''
target {
    type testtype;
	class pkgcore.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    ref target target;
	inline {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	} {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	};
	mix target {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	};
}
'''))
		manager = central.ConfigManager(
			[{'testtype': basics.ConfigType('testtype',	{'hi': 'str'})}],
			[config])
		section = config['test']
		for name in ('ref', 'inline', 'mix'):
			try:
				section.get_value(manager, name, 'section_ref')
			except errors.ConfigurationError, e:
				self.assertEquals('only one argument required', str(e))
			else:
				self.fail('no exception raised')

	def test_section_refs(self):
		config = dhcpformat.configFromFile(StringIO('''
target {
    type testtype;
	class pkgcore.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    refs target {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	};
}
'''))
		manager = central.ConfigManager(
			[{'testtype': basics.ConfigType('testtype',	{'hi': 'str'})}],
			[config])
		section = config['test']
		self.assertEquals(
			section.get_value(manager, 'refs', 'section_refs'),
			[((), {'hi': 'there'}),
			 ((), {'hi': 'here'})])

	def test_one_section_refs(self):
		config = dhcpformat.configFromFile(StringIO('''
target {
    type testtype;
	class pkgcore.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    inline {
	    type testtype;
		class pkgcore.test.config.test_dhcpformat.passthrough;
		hi here;
	};
	ref target;
}
'''))
		manager = central.ConfigManager(
			[{'testtype': basics.ConfigType('testtype',	{'hi': 'str'})}],
			[config])
		section = config['test']
		self.assertEquals(
			section.get_value(manager, 'inline', 'section_refs'),
			[((), {'hi': 'here'})])
		self.assertEquals(
			section.get_value(manager, 'ref', 'section_refs'),
			[((), {'hi': 'there'})])

	def test_invalid_values(self):
		config = dhcpformat.configFromFile(StringIO('''
test {
    bool maybe;
	string la la;
	ref one two;
	callable pkgcore.config.dhcpformat;
	inlinecallable { lala bork; };
}
'''))
		section = config['test']
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, None, 'bool', 'bool')
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, None, 'string', 'str')
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, None, 'callable', 'callable')
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, None, 'ref', 'section_ref')
		self.assertRaises(
			errors.ConfigurationError,
			section.get_value, None, 'inlinecallable', 'callable')
