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


class ConfigFromIniTest(unittest.TestCase):

    def test_config_from_ini(self):
        config = cparser.config_from_file(StringIO('''
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
        config = cparser.config_from_file(StringIO('''
[test]
ref = 'missing'
'''))
        section = config['test']
        self.assertRaises(
            errors.ConfigurationError,
            section.get_value,
            central.ConfigManager([]), 'ref', 'section_ref')
