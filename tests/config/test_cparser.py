import sys
import textwrap
from io import StringIO

import pytest
from pkgcore.config import central, cparser, errors


def test_case_sensitive_config_parser():
    cp = cparser.CaseSensitiveConfigParser()
    config = StringIO('\n'.join((
        '[header]',
        'foo=bar',
        'FOO=BAR',
        '[HEADER]',
        'foo=notbar',
    )))
    cp.read_file(config)
    assert cp.get('header', 'foo') == 'bar'
    assert cp.get('header', 'FOO') == 'BAR'
    assert cp.get('HEADER', 'foo') == 'notbar'


class TestConfigFromIni:

    def test_config_from_ini(self):
        config = cparser.config_from_file(StringIO(textwrap.dedent('''\
            [test]
            string = 'hi I am a string'
            list = foo bar baz
            list.prepend = pre bits
            list.append = post bits
            true = yes
            false = no
        ''')))
        assert list(config.keys()) == ['test']
        section = config['test']
        for key, arg_type, value in (
            ('string', 'str', [None, 'hi I am a string', None]),
            ('list', 'list', [
                    ['pre', 'bits'], ['foo', 'bar', 'baz'], ['post', 'bits']]),
            ('true', 'bool', True),
            ('false', 'bool', False),
            ):
            assert section.render_value(None, key, arg_type) == value

    def test_missing_section_ref(self):
        config = cparser.config_from_file(StringIO(textwrap.dedent('''\
            [test]
            ref = 'missing'
        ''')))
        section = config['test']
        with pytest.raises(errors.ConfigurationError):
            section.render_value(central.ConfigManager([]), 'ref', 'ref:drawer').collapse()
