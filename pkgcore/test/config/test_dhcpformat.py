# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from StringIO import StringIO

from pkgcore.test import TestCase

try:
    import pyparsing
except ImportError:
    skip_test = 'Missing pyparsing module.'
else:
    if getattr(pyparsing, 'pythonStyleComment', None) is None:
        skip_test = 'pyparsing missing pythonStyleComment. Upgrade to >=1.4'
    else:
        skip_test = None
        from pkgcore.config import dhcpformat, mke2fsformat

from pkgcore.config import central, errors, configurable


def passthrough(*args, **kwargs):
    return args, kwargs

@configurable(types={'hi': 'str'}, typename='test')
def testtype(*args, **kwargs):
    return args, kwargs


class PyParsingTest(TestCase):
    if skip_test is not None:
        skip = skip_test

    def test_basics(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
test {
    hi there;
}
'''),
            (mke2fsformat.config_from_file, '''
[test]
    hi = there
'''),
            ]:
            config = parser(StringIO(text))
            self.assertEqual(config.keys(), ['test'])
            section = config['test']
            self.failUnless('hi' in section)
            self.assertEqual(section.keys(), ['hi'])
            self.assertEqual(section.get_value(None, 'hi', 'str'), 'there')

    def test_basic_types(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
test {
    list one two three;
    string hi;
    bool yes;
    callable pkgcore.test.config.test_dhcpformat.passthrough;
}
'''),
            (mke2fsformat.config_from_file, '''
[test]
    list = one two three
    string = hi
    bool = yes
    callable = pkgcore.test.config.test_dhcpformat.passthrough
'''),
            ]:
            config = parser(StringIO(text))
            section = config['test']
            for name, typename, value in (
                ('list', 'list', ['one', 'two', 'three']),
                ('string', 'str', 'hi'),
                ('bool', 'bool', True),
                ('callable', 'callable', passthrough),
                ):
                self.assertEqual(section.get_value(None, name, typename),
                                  value)
            for name, typename, value in (
                ('list', 'list', ['one', 'two', 'three']),
                ('string', 'str', 'hi'),
                ('bool', 'str', 'yes'),
                ('callable', 'str',
                 'pkgcore.test.config.test_dhcpformat.passthrough'),
                ):
                self.assertEqual(
                    (typename, value), section.get_value(None, name, 'repr'))

    def test_section_ref(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
target {
    class pkgcore.test.config.test_dhcpformat.testtype;
    hi there;
}

test {
    ref target;
    inline {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    };
}
'''),
            (mke2fsformat.config_from_file, '''
[target]
    class = pkgcore.test.config.test_dhcpformat.testtype
    hi = there

[test]
    ref = target
    inline = {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    }
'''),
            ]:
            config = parser(StringIO(text))
            manager = central.ConfigManager([config])
            section = config['test']
            self.assertEqual(
                section.get_value(manager, 'ref', 'ref:test').instantiate(),
                ((), {'hi': 'there'}))
            self.assertEqual(
                section.get_value(
                    manager, 'inline', 'ref:test').instantiate(),
                ((), {'hi': 'here'}))
            kind, ref = section.get_value(manager, 'inline', 'repr')
            self.assertEqual('ref', kind)
            self.assertEqual('here', ref.get_value(None, 'hi', 'str'))

    def test_multiple_section_ref(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
target {
    class pkgcore.test.config.test_dhcpformat.testtype;
    hi there;
}

test {
    ref target target;
    inline {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    } {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    };
    mix target {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    };
}
'''),
            (mke2fsformat.config_from_file, '''
[target]
    class = pkgcore.test.config.test_dhcpformat.testtype
    hi = there

[test]
    ref = target target
    inline = {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    } {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    }
    mix = target {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    }
'''),
            ]:
            config = parser(StringIO(text))
            manager = central.ConfigManager([config])
            section = config['test']
            for name in ('ref', 'inline', 'mix'):
                try:
                    section.get_value(manager, name, 'ref:test')
                except errors.ConfigurationError, e:
                    self.assertEqual('only one argument required', str(e))
                else:
                    self.fail('no exception raised')
            kind, refs = section.get_value(manager, 'mix', 'repr')
            self.assertEqual('refs', kind)
            self.assertEqual(2, len(refs))
            self.assertEqual('target', refs[0])
            self.assertEqual('here', refs[1].get_value(None, 'hi', 'str'))

    def test_section_refs(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
target {
    class pkgcore.test.config.test_dhcpformat.testtype;
    hi there;
}

test {
    refs target {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    };
}
'''),
            (mke2fsformat.config_from_file, '''
[target]
    class = pkgcore.test.config.test_dhcpformat.testtype
    hi = there

[test]
    refs = target {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    }
'''),
            ]:
            config = parser(StringIO(text))
            manager = central.ConfigManager([config])
            section = config['test']
            refs = section.get_value(manager, 'refs', 'refs:test')
            self.assertEqual(((), {'hi': 'there'}), refs[0].instantiate())
            self.assertEqual(((), {'hi': 'here'}), refs[1].instantiate())

    def test_one_section_refs(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
target {
    class pkgcore.test.config.test_dhcpformat.testtype;
    hi there;
}

test {
    inline {
        class pkgcore.test.config.test_dhcpformat.testtype;
        hi here;
    };
    ref target;
}
'''),
            (mke2fsformat.config_from_file, '''
[target]
    class = pkgcore.test.config.test_dhcpformat.testtype
    hi = there

[test]
    inline = {
        class = pkgcore.test.config.test_dhcpformat.testtype
        hi = here
    }
    ref = target
'''),
            ]:
            config = parser(StringIO(text))
            manager = central.ConfigManager([config])
            section = config['test']
            self.assertEqual(
                section.get_value(
                    manager, 'inline', 'refs:test')[0].instantiate(),
                ((), {'hi': 'here'}))
            self.assertEqual(
                section.get_value(
                    manager, 'ref', 'refs:test')[0].instantiate(),
                ((), {'hi': 'there'}))

    def test_invalid_values(self):
        for parser, text in [
            (dhcpformat.config_from_file, '''
test {
    bool maybe;
    string la la;
    ref one two;
    callable pkgcore.config.dhcpformat;
    borkedimport pkgcore.config.dhcpformat.spork;
    inlinecallable { lala bork; };
}
'''),
            (mke2fsformat.config_from_file, '''
[test]
    bool = maybe
    string = la la
    ref = one two
    callable = pkgcore.config.dhcpformat
    borkedimport = pkgcore.config.dhcpformat.spork
    inlinecallable = {
        lala = bork
    }
'''),
            ]:
            section = parser(StringIO(text))['test']
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
                section.get_value, None, 'borkedimport', 'callable')
            self.assertRaises(
                errors.ConfigurationError,
                section.get_value, None, 'ref', 'ref:test')
            self.assertRaises(
                errors.ConfigurationError,
                section.get_value, None, 'inlinecallable', 'callable')
            self.assertRaises(
                errors.ConfigurationError,
                section.get_value, None, 'string', 'callable')
            self.assertRaises(
                errors.ConfigurationError,
                section.get_value, None, 'inlinecallable', 'bool')

    def test_error(self):
        for parser, text in [
            (dhcpformat.config_from_file, 'test {'),
            (mke2fsformat.config_from_file, '[test'),
            ]:
            self.assertRaises(
                errors.ConfigurationError,
                parser, StringIO(text))
