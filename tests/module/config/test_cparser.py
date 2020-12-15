import sys
from io import StringIO

from snakeoil.test import TestCase

from pkgcore.config import central, cparser, errors


class CaseSensitiveConfigParserTest(TestCase):

    def test_case_sensitivity(self):
        cp = cparser.CaseSensitiveConfigParser()
        config = StringIO('\n'.join((
            '[header]',
            'foo=bar',
            'FOO=BAR',
            '[HEADER]',
            'foo=notbar',
            )))
        if sys.hexversion < 0x03020000:
            cp.readfp(config)
        else:
            cp.read_file(config)
        self.assertEqual(cp.get('header', 'foo'), 'bar')
        self.assertEqual(cp.get('header', 'FOO'), 'BAR')
        self.assertEqual(cp.get('HEADER', 'foo'), 'notbar')


class ConfigFromIniTest(TestCase):

    def test_config_from_ini(self):
        config = cparser.config_from_file(StringIO('''
[test]
string = 'hi I am a string'
list = foo bar baz
list.prepend = pre bits
list.append = post bits
true = yes
false = no
'''))
        self.assertEqual(list(config.keys()), ['test'])
        section = config['test']
        for key, arg_type, value in [
            ('string', 'str', [None, 'hi I am a string', None]),
            ('list', 'list', [
                    ['pre', 'bits'], ['foo', 'bar', 'baz'], ['post', 'bits']]),
            ('true', 'bool', True),
            ('false', 'bool', False),
            ]:
            self.assertEqual(section.render_value(None, key, arg_type), value)

    def test_missing_section_ref(self):
        config = cparser.config_from_file(StringIO('''
[test]
ref = 'missing'
'''))
        section = config['test']
        self.assertRaises(
            errors.ConfigurationError,
            section.render_value(
                central.ConfigManager([]), 'ref', 'ref:drawer').collapse)
