# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import os
import tempfile

from pkgcore.test import TestCase

from pkgcore.config import basics, errors, ConfigHint, configurable


def passthrough(*args, **kwargs):
    return args, kwargs


class ConfigTypeTest(TestCase):

    def test_invalid_types(self):
        for var in ('class', 'inherit'):
            @configurable({var: 'str'})
            def testtype():
                pass
            self.assertRaises(
                errors.TypeDefinitionError, basics.ConfigType, testtype)
        @configurable(positional=['foo'])
        def test(*args):
            pass
        self.assertRaises(errors.TypeDefinitionError, basics.ConfigType, test)


# the docstrings aren't part of the test, but using 'pass' instead
# makes trial's --coverage complain about them.

def argsfunc(*args):
    """Function taking a variable number of arguments."""

def kwargsfunc(**kwargs):
    """Function taking keyword arguments."""


def nonopt(one, two):
    """Function taking two non-optional args."""


def alltypes(alist=(), astr='astr', abool=True, aref=object(), anint=3,
    along=long(3)):
    """Function taking lots of kinds of args."""


class NewStyleStrClass(object):

    def __init__(self, one, two='two'):
        """Newstyle testclass."""

    def test_member(self, one):
        """Newstyle memberfunc."""


class NewStyleClass(object):

    def __init__(self, one, two=object()):
        """Newstyle testclass."""

    def member(self, one):
        """Newstyle memberfunc."""


class OldStyleClass:

    def __init__(self, one, two=object()):
        """Newstyle testclass."""

    def member(self, one):
        """Newstyle memberfunc."""


class ConfigTypeFromFunctionTest(TestCase):

    def test_invalid(self):
        self.assertRaises(TypeError, basics.ConfigType, argsfunc)
        self.assertRaises(TypeError, basics.ConfigType, kwargsfunc)

    def test_basic(self):
        nonopt_type = basics.ConfigType(nonopt)
        self.assertEqual(nonopt_type.name, 'nonopt')
        self.assertEqual(
            nonopt_type.types,
            {'one': 'str', 'two': 'str'})
        self.assertEqual(nonopt_type.incrementals, [])
        self.assertEqual(nonopt_type.required, ('one', 'two'))
        self.assertEqual(nonopt_type.positional, ('one', 'two'))

    def test_default_types(self):
        test_type = basics.ConfigType(alltypes)
        self.assertEqual(
            test_type.types,
            {'alist': 'list', 'astr': 'str', 'abool': 'bool',
             'aref': 'section_ref', 'anint': 'int', 'along': 'int'})
        self.assertEqual(test_type.required, ())

    def _test_class_member(self, func):
        test_type = basics.ConfigType(func)
        self.assertEqual(test_type.name, 'member')
        self.assertEqual(test_type.required, ('one',))

    def test_newstyle_instance(self):
        self._test_class_member(NewStyleClass(1).member)

    def test_oldstyle_instance(self):
        self._test_class_member(OldStyleClass(1).member)

    def test_newstyle_class(self):
        self._test_class_member(NewStyleClass.member)

    def test_oldstyle_class(self):
        self._test_class_member(OldStyleClass.member)


class ConfigTypeFromClassTest(TestCase):

    def _test_basics(self, klass, name, two_override='section_ref'):
        test_type = basics.ConfigType(klass)
        self.assertEqual(test_type.name, name)
        self.assertEqual(sorted(test_type.required), ['one'])
        self.assertEqual(
            test_type.types,
            {'one': 'str', 'two': two_override})

    def test_oldstyle(self):
        self._test_basics(OldStyleClass, 'OldStyleClass')

    def test_newstyle(self):
        self._test_basics(NewStyleClass, 'NewStyleClass')

    def test_defaults_str(self):
        self._test_basics(NewStyleStrClass, 'NewStyleStrClass',
                          two_override='str')

    def test_config_hint(self):
        class Class(NewStyleClass):
            pkgcore_config_type = ConfigHint(types={'two':'bool'})
        self._test_basics(Class, 'Class', two_override='bool')


class ConfigHintDecoratorTest(TestCase):

    def test_configurable(self):
        @configurable(typename='spork', types={'foon': 'str'})
        def stuff(*args, **kwargs):
            return args, kwargs

        self.assertEqual('spork', stuff.pkgcore_config_type.typename)
        self.assertEqual('str', basics.ConfigType(stuff).types['foon'])
        self.assertEqual((('spork',), {}), stuff('spork'))


class ConfigHintCloneTest(TestCase):

    def test_clone(self):
        c = ConfigHint(types={'foo':'list', 'one':'str'},
            positional=['one'], required=['one'],
            incrementals=['foo'], typename='barn')
        c2 = c.clone(types={'foo':'list', 'one':'str', 'two':'str'},
            required=['one', 'two'])
        self.assertEqual(c2.types, {'foo':'list', 'one':'str', 'two':'str'})
        self.assertEqual(c2.positional, c.positional)
        self.assertEqual(c2.required, ['one', 'two'])
        self.assertEqual(c2.incrementals, c.incrementals)
        self.assertEqual(c2.typename, c.typename)
        self.assertEqual(c2.allow_unknowns, c.allow_unknowns)


class ConfigSectionTest(TestCase):

    def test_basics(self):
        section = basics.ConfigSection()
        self.assertRaises(NotImplementedError, section.__contains__, 42)
        self.assertRaises(NotImplementedError, section.keys)
        self.assertRaises(
            NotImplementedError, section.get_value, None, 'a', 'str')


class ConfigSectionFromStringDictTest(TestCase):

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
        self.section = basics.ConfigSectionFromStringDict(self.source)

    def test_contains(self):
        self.failIf('foo' in self.section)
        self.failUnless('list' in self.section)

    def test_keys(self):
        self.assertEqual(
            sorted(self.section.keys()), ['bool', 'callable', 'list', 'str'])

    def test_get_value(self):
        # valid gets
        for typename, value in self.destination.iteritems():
            self.assertEqual(
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
            {'goodref': 'target', 'badref': 'missing'})
        target_config = object()
        class TestCentral(object):
            def collapse_named_section(self, section):
                try:
                    return {'target': target_config}[section]
                except KeyError:
                    raise errors.ConfigurationError(section)
        self.assertEqual(
            section.get_value(
                TestCentral(), 'goodref', 'section_ref').collapse(),
            target_config)
        self.assertRaises(
            errors.ConfigurationError,
            section.get_value(
                TestCentral(), 'badref', 'section_ref').instantiate)

    def test_section_refs(self):
        section = basics.ConfigSectionFromStringDict(
            {'goodrefs': '1 2', 'badrefs': '2 3'})
        config1 = object()
        config2 = object()
        class TestCentral(object):
            def collapse_named_section(self, section):
                try:
                    return {'1': config1, '2': config2}[section]
                except KeyError:
                    raise errors.ConfigurationError(section)
        self.assertEqual(
            list(ref.collapse() for ref in section.get_value(
                    TestCentral(), 'goodrefs', 'section_refs')),
            [config1, config2])
        lazy_refs = section.get_value(TestCentral(), 'badrefs', 'section_refs')
        self.assertEqual(2, len(lazy_refs))
        self.assertRaises(errors.ConfigurationError, lazy_refs[1].collapse)


class HardCodedConfigSectionTest(TestCase):

    def setUp(self):
        self.source = {
            'str': 'pkgcore.test',
            'bool': True,
            'list': ['0', '1', '2'],
            'callable': passthrough,
            }
        self.section = basics.HardCodedConfigSection(self.source)

    def test_contains(self):
        self.failIf('foo' in self.section)
        self.failUnless('str' in self.section)

    def test_keys(self):
        self.assertEqual(
            sorted(self.section.keys()), ['bool', 'callable', 'list', 'str'])

    def test_get_value(self):
        # try all combinations
        for arg, value in self.source.iteritems():
            for typename in self.source:
                if arg == typename:
                    self.assertEqual(
                        value, self.section.get_value(None, arg, typename))
                else:
                    self.assertRaises(
                        errors.ConfigurationError,
                        self.section.get_value, None, arg, typename)

    def test_section_ref(self):
        ref = basics.HardCodedConfigSection({})
        section = basics.HardCodedConfigSection({'ref': 42, 'ref2': ref})
        self.assertRaises(errors.ConfigurationError,
            section.get_value, None, 'ref', 'section_ref')
        self.assertIdentical(
            ref,
            section.get_value(None, 'ref2', 'section_ref').section)

    def test_section_refs(self):
        ref = basics.HardCodedConfigSection({})
        section = basics.HardCodedConfigSection({'refs': [1, 2],
                                                 'refs2': [ref]})
        self.assertRaises(errors.ConfigurationError,
            section.get_value, None, 'refs', 'section_refs')
        self.assertIdentical(
            ref,
            section.get_value(None, 'refs2', 'section_refs')[0].section)


class AliasTest(TestCase):

    def test_alias(self):
        foon = object()
        class MockManager(object):
            def collapse_named_section(self, name):
                if name == 'foon':
                    return foon
                return object()
        manager = MockManager()
        alias = basics.section_alias('foon', 'spork')
        type_obj = basics.ConfigType(alias.get_value(manager, 'class',
                                                     'callable'))
        self.assertEqual('spork', type_obj.name)
        self.assertIdentical(
            foon,
            alias.get_value(manager, 'target', 'section_ref').collapse())
        alias = basics.section_alias('foon')
        type_obj = basics.ConfigType(alias.get_value(manager, 'class',
                                                     'callable'))
        self.assertEqual('alias', type_obj.name)
        self.assertIdentical(
            foon,
            alias.get_value(manager, 'target', 'section_ref').collapse())


class ParsersTest(TestCase):

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

    def test_int_parser(self):
        for string, output in [
            ('\t 1', 1),
            ('1', 1),
            ('-100', -100)]:
            self.assertEqual(basics.int_parser(string), output)

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
            self.assertEqual(basics.str_parser(string), output)

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
            self.assertEqual(basics.list_parser(string), output)
        for string in ['"', "'foo", 'ba"r', 'baz"']:
            self.assertRaises(
                errors.QuoteInterpretationError, basics.list_parser, string)
        # make sure this explodes instead of returning something
        # confusing so we explode much later
        self.assertRaises(TypeError, basics.list_parser, ['no', 'string'])


class LoaderTest(TestCase):

    def setUp(self):
        fd, self.name = tempfile.mkstemp()
        f = os.fdopen(fd, 'w')
        f.write('foon')
        f.close()

    def tearDown(self):
        os.remove(self.name)

    def test_parse_config_file(self):
        self.assertRaises(
            errors.InstantiationError,
            basics.parse_config_file, '/spork', None)
        def parser(f):
            return f.read()
        self.assertEqual('foon', basics.parse_config_file(self.name, parser))
