# Copyright: 2005 Gentoo Foundation
# License: GPL2


from StringIO import StringIO

from twisted.trial import unittest

try:
	import pyparsing
	skip_test = False
except ImportError:
	skip_test = True
	
if not skip_test:
	from portage.config import dhcpformat

from portage.config import central, basics, errors

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
	callable portage.test.config.test_dhcpformat.passthrough;
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
	class portage.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    ref target;
	inline {
	    type testtype;
		class portage.test.config.test_dhcpformat.passthrough;
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

	test_section_ref.todo = (errors.ConfigurationError, 'does not work yet')
		
	def test_section_refs(self):
		config = dhcpformat.configFromFile(StringIO('''
target {
    type testtype;
	class portage.test.config.test_dhcpformat.passthrough;
    hi there;
}

test {
    refs target {
	    type testtype;
		class portage.test.config.test_dhcpformat.passthrough;
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

	def test_invalid_values(self):
		config = dhcpformat.configFromFile(StringIO('''
test {
    bool maybe;
	string la la;
	ref one two;
	callable portage.config.dhcpformat;
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

