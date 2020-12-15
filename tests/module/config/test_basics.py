import os
import tempfile

from snakeoil.test import TestCase

from pkgcore.config import basics, central, errors
from pkgcore.config.hint import ConfigHint, configurable


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
    along=int(3)):
    """Function taking lots of kinds of args."""


class NewStyleStrClass:

    def __init__(self, one, two='two'):
        """Newstyle testclass."""

    def test_member(self, one):
        """Newstyle memberfunc."""


class NewStyleClass:

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
        self.assertEqual(nonopt_type.required, ('one', 'two'))
        self.assertEqual(nonopt_type.positional, ('one', 'two'))

    def test_default_types(self):
        test_type = basics.ConfigType(alltypes)
        self.assertEqual(
            test_type.types,
            {'alist': 'list', 'astr': 'str', 'abool': 'bool',
             'anint': 'int', 'along': 'int'})
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

    def _test_basics(self, klass, name, two_override=None):
        test_type = basics.ConfigType(klass)
        self.assertEqual(test_type.name, name)
        self.assertEqual(sorted(test_type.required), ['one'])
        target_types = {'one': 'str'}
        if two_override is not None:
            target_types['two'] = two_override
        self.assertEqual(target_types, test_type.types)
        self.assertEqual(test_type.name, name)

    def test_oldstyle(self):
        self._test_basics(OldStyleClass, 'OldStyleClass')

    def test_newstyle(self):
        self._test_basics(NewStyleClass, 'NewStyleClass')

    def test_defaults_str(self):
        self._test_basics(NewStyleStrClass, 'NewStyleStrClass',
                          two_override='str')

    def test_config_hint(self):
        class Class(NewStyleClass):
            pkgcore_config_type = ConfigHint(
                types={'two':'bool'}, doc='interesting')
        self._test_basics(Class, 'Class', two_override='bool')
        self.assertEqual('interesting', basics.ConfigType(Class).doc)

    def test_object_init(self):
        class kls:
            pass
        conf = basics.ConfigType(kls)
        self.assertEqual(conf.types, {})
        self.assertEqual(conf.required, ())

    def test_builtin_targets(self):
        # ensure it's a type error, rather than an attributeerror
        # from not being able to pull func_code
        self.assertRaises(TypeError,
            basics.ConfigType, dict)

    def test_builtin_full_override(self):
        # check our assumptions...
        # and yes, the signatures below are for file rather than
        # dict; we need a cpy class for the test, the ConfigHint doesn't
        # have to be accurate however
        class cls(dict):
            __slots__ = ()
        self.assertRaises(TypeError, basics.ConfigType, cls)

        raw_hint = ConfigHint(types={"filename":"str", "mode":"r",
            "buffering":"int"}, typename='file',
            required=['filename'], positional=['filename'])

        # make sure it still tries to introspect, and throws typeerror.
        # introspection is generally wanted- if it must be skipped, the
        # ConfigHint must make it explicit
        cls.pkgcore_config_type = raw_hint
        self.assertRaises(TypeError, basics.ConfigType, cls)
        cls.pkgcore_config_type = raw_hint.clone(authorative=True)
        conf = basics.ConfigType(cls)
        self.assertEqual(conf.name, 'file')
        self.assertEqual(list(conf.required), ['filename'])
        self.assertEqual(list(conf.positional), ['filename'])
        self.assertEqual(sorted(conf.types), ['buffering', 'filename', 'mode'])



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
            typename='barn', doc='orig doc')
        c2 = c.clone(types={'foo':'list', 'one':'str', 'two':'str'},
            required=['one', 'two'])
        self.assertEqual(c2.types, {'foo':'list', 'one':'str', 'two':'str'})
        self.assertEqual(c2.positional, c.positional)
        self.assertEqual(c2.required, ['one', 'two'])
        self.assertEqual(c2.typename, c.typename)
        self.assertEqual(c2.allow_unknowns, c.allow_unknowns)
        self.assertEqual(c2.doc, c.doc)


class SectionRefTest(TestCase):

    # Silly testcase just to make something drop off the --coverage radar.

    def test_collapse(self):
        ref = basics.LazySectionRef(None, 'ref:foon')
        self.assertRaises(NotImplementedError, ref._collapse)
        self.assertRaises(NotImplementedError, ref.collapse)
        self.assertRaises(NotImplementedError, ref.instantiate)


class ConfigSectionTest(TestCase):

    def test_basics(self):
        section = basics.ConfigSection()
        self.assertRaises(NotImplementedError, section.__contains__, 42)
        self.assertRaises(NotImplementedError, section.keys)
        self.assertRaises(
            NotImplementedError, section.render_value, None, 'a', 'str')


class DictConfigSectionTest(TestCase):

    def test_misc(self):
        def convert(central, value, arg_type):
            return central, value, arg_type
        section = basics.DictConfigSection(convert, {'list': [1, 2]})
        self.assertFalse('foo' in section)
        self.assertTrue('list' in section)
        self.assertEqual(['list'], list(section.keys()))
        self.assertEqual(
            (None, [1, 2], 'spoon'), section.render_value(None, 'list', 'spoon'))

    def test_failure(self):
        def fail(central, value, arg_type):
            raise errors.ConfigurationError('fail')
        section = basics.DictConfigSection(fail, {'list': [1, 2]})
        self.assertRaises(
            errors.ConfigurationError,
            section.render_value, None, 'list', 'spoon')


class FakeIncrementalDictConfigSectionTest(TestCase):

    @staticmethod
    def _convert(central, value, arg_type):
        return central, value, arg_type

    @staticmethod
    def _fail(central, value, arg_type):
        raise errors.ConfigurationError('fail')

    def test_misc(self):
        section = basics.FakeIncrementalDictConfigSection(
            self._convert, {'list': [1, 2]})
        self.assertFalse('foo' in section)
        self.assertTrue('list' in section)
        self.assertEqual(['list'], list(section.keys()))
        self.assertRaises(
            errors.ConfigurationError,
            basics.FakeIncrementalDictConfigSection(
                self._fail, {'a': 'b'}).render_value,
            None, 'a', 'str')

    def test_fake_incrementals(self):
        section = basics.FakeIncrementalDictConfigSection(
            self._convert, {'seq.append': [1, 2]})
        manager = object()
        self.assertEqual(
            [None, None, (manager, [1, 2], 'list')],
            section.render_value(manager, 'seq', 'list'))
        def _repr(central, value, arg_type):
            return 'list', ['thing']
        section = basics.FakeIncrementalDictConfigSection(
            _repr, {'foo': None})
        self.assertEqual(
            ('list', (None, ['thing'], None)),
            section.render_value(manager, 'foo', 'repr'))
        self.assertRaises(
            errors.ConfigurationError,
            basics.FakeIncrementalDictConfigSection(
                self._fail, {'a.prepend': 'b'}).render_value,
            None, 'a', 'list')

    def test_repr(self):
        def asis(central, value, arg_type):
            assert arg_type == 'repr', arg_type
            return value
        section = basics.FakeIncrementalDictConfigSection(
            asis, {'seq.append': ('list', [1, 2]),
                   'simple': ('bool', True),
                   'multistr': ('str', 'body'),
                   'multistr.prepend': ('str', 'head'),
                   'refs': ('str', 'lost'),
                   'refs.append': ('ref', 'main'),
                   'refs.prepend': ('refs', ['a', 'b']),
                   'strlist': ('callable', asis),
                   'strlist.prepend': ('str', 'whatever'),
                   'wrong.prepend': ('wrong', 'wrong'),
                   })
        manager = object()
        self.assertRaises(
            KeyError, section.render_value, manager, 'spoon', 'repr')
        self.assertEqual(
            ('list', [None, None, [1, 2]]),
            section.render_value(manager, 'seq', 'repr'))
        self.assertEqual(
            ('bool', True), section.render_value(manager, 'simple', 'repr'))
        self.assertEqual(
            ('str', ['head', 'body', None]),
            section.render_value(manager, 'multistr', 'repr'))
        self.assertEqual(
            ('refs', [['a', 'b'], ['lost'], ['main']]),
            section.render_value(manager, 'refs', 'repr'))
        self.assertEqual(
            ('list', [
                    ['whatever'],
                    ['module.config.test_basics.asis'],
                    None]),
            section.render_value(manager, 'strlist', 'repr'))
        self.assertRaises(
            errors.ConfigurationError,
            section.render_value, manager, 'wrong', 'repr')


class ConvertStringTest(TestCase):

    def test_render_value(self):
        source = {
            'str': 'tests',
            'bool': 'yes',
            'list': '0 1 2',
            'callable': 'module.config.test_basics.passthrough',
            }
        destination = {
            'str': 'tests',
            'bool': True,
            'list': ['0', '1', '2'],
            'callable': passthrough,
            }

        # valid gets
        for typename, value in destination.items():
            self.assertEqual(
                value,
                basics.convert_string(None, source[typename], typename))

        # reprs
        for typename, value in source.items():
            self.assertEqual(
                ('str', value),
                basics.convert_string(None, source[typename], 'repr'))
        # invalid gets
        # not callable
        self.assertRaises(
            errors.ConfigurationError,
            basics.convert_string, None, source['str'], 'callable')
        # not importable
        self.assertRaises(
            errors.ConfigurationError,
            basics.convert_string, None, source['bool'], 'callable')
        # Bogus type.
        self.assertRaises(
            errors.ConfigurationError,
            basics.convert_string, None, source['bool'], 'frob')

    def test_section_ref(self):
        def spoon():
            """Noop."""
        target_config = central.CollapsedConfig(
            basics.ConfigType(spoon), {}, None)
        class TestCentral:
            def collapse_named_section(self, section):
                try:
                    return {'target': target_config}[section]
                except KeyError:
                    raise errors.ConfigurationError(section)
        self.assertEqual(
            basics.convert_string(
                TestCentral(), 'target', 'ref:spoon').collapse(),
            target_config)
        self.assertRaises(
            errors.ConfigurationError,
            basics.convert_string(
                TestCentral(), 'missing', 'ref:spoon').instantiate)

    def test_section_refs(self):
        def spoon():
            """Noop."""
        config1 = central.CollapsedConfig(
            basics.ConfigType(spoon), {}, None)
        config2 = central.CollapsedConfig(
            basics.ConfigType(spoon), {}, None)
        class TestCentral:
            def collapse_named_section(self, section):
                try:
                    return {'1': config1, '2': config2}[section]
                except KeyError:
                    raise errors.ConfigurationError(section)
        self.assertEqual(
            list(ref.collapse() for ref in basics.convert_string(
                    TestCentral(), '1 2', 'refs:spoon')),
            [config1, config2])
        lazy_refs = basics.convert_string(TestCentral(), '2 3', 'refs:spoon')
        self.assertEqual(2, len(lazy_refs))
        self.assertRaises(errors.ConfigurationError, lazy_refs[1].collapse)


class ConvertAsIsTest(TestCase):

    source = {
        'str': 'tests',
        'bool': True,
        'list': ['0', '1', '2'],
        'callable': passthrough,
        }

    def test_render_value(self):
        # try all combinations
        for arg, value in self.source.items():
            for typename in self.source:
                if arg == typename:
                    self.assertEqual(
                        value, basics.convert_asis(None, value, typename))
                else:
                    self.assertRaises(
                        errors.ConfigurationError,
                        basics.convert_asis, None, value, typename)

    def test_repr(self):
        for typename, value in self.source.items():
            self.assertEqual(
                (typename, value),
                basics.convert_asis(None, value, 'repr'))
        self.assertRaises(
            errors.ConfigurationError,
            basics.convert_asis, None, object(), 'repr')

    def test_section_ref(self):
        ref = basics.HardCodedConfigSection({})
        self.assertRaises(errors.ConfigurationError,
            basics.convert_asis, None, 42, 'ref:spoon')
        self.assertIdentical(
            ref, basics.convert_asis(None, ref, 'ref:spoon').section)
        self.assertEqual(
            ('ref', ref), basics.convert_asis(None, ref, 'repr'))

    def test_section_refs(self):
        ref = basics.HardCodedConfigSection({})
        self.assertRaises(errors.ConfigurationError,
            basics.convert_asis, None, [1, 2], 'refs:spoon')
        self.assertIdentical(
            ref,
            basics.convert_asis(None, [ref], 'refs:spoon')[0].section)
        self.assertEqual(
            ('refs', [ref]), basics.convert_asis(None, [ref], 'repr'))


class AliasTest(TestCase):

    def test_alias(self):
        def spoon():
            """Noop."""
        foon = central.CollapsedConfig(basics.ConfigType(spoon), {}, None)
        class MockManager:
            def collapse_named_section(self, name):
                if name == 'foon':
                    return foon
                return object()
        manager = MockManager()
        alias = basics.section_alias('foon', 'spoon')
        type_obj = basics.ConfigType(alias.render_value(manager, 'class',
                                                     'callable'))
        self.assertEqual('spoon', type_obj.name)
        self.assertIdentical(
            foon,
            alias.render_value(manager, 'target', 'ref:spoon').collapse())


class ParsersTest(TestCase):

    def test_str_to_bool(self):
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
            self.assertIdentical(basics.str_to_bool(string), output)

    def test_str_to_int(self):
        for string, output in [
            ('\t 1', 1),
            ('1', 1),
            ('-100', -100)]:
            self.assertEqual(basics.str_to_int(string), output)
        self.assertRaises(errors.ConfigurationError, basics.str_to_int, 'f')

    def test_str_to_str(self):
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
            self.assertEqual(basics.str_to_str(string), output)

    def test_str_to_list(self):
        for string, output in [
            ('foo', ['foo']),
            ('"f\'oo"  \'b"ar\'', ["f'oo", 'b"ar']),
            ('', []),
            (' ', []),
            ('\\"hi ', ['"hi']),
            ('\'"hi\'', ['"hi']),
            ('"\\"hi"', ['"hi']),
            ]:
            self.assertEqual(basics.str_to_list(string), output)
        for string in ['"', "'foo", 'ba"r', 'baz"']:
            self.assertRaises(
                errors.QuoteInterpretationError, basics.str_to_list, string)
        # make sure this explodes instead of returning something
        # confusing so we explode much later
        self.assertRaises(TypeError, basics.str_to_list, ['no', 'string'])


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
            errors.ConfigurationError,
            basics.parse_config_file, '/spork', None)
        def parser(f):
            return f.read()
        self.assertEqual('foon', basics.parse_config_file(self.name, parser))
