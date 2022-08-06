import pytest

from pkgcore.config import basics, central, errors
from pkgcore.config.hint import ConfigHint, configurable


def passthrough(*args, **kwargs):
    return args, kwargs


def test_invalid_config_types():
    for var in ('class', 'inherit'):
        @configurable({var: 'str'})
        def testtype():
            pass
        with pytest.raises(errors.TypeDefinitionError):
            basics.ConfigType(testtype)
    @configurable(positional=['foo'])
    def test(*args):
        pass
    with pytest.raises(errors.TypeDefinitionError):
        basics.ConfigType(test)


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


class TestConfigTypeFromFunction:

    def test_invalid(self):
        with pytest.raises(TypeError):
            basics.ConfigType(argsfunc)
        with pytest.raises(TypeError):
            basics.ConfigType(kwargsfunc)

    def test_basic(self):
        nonopt_type = basics.ConfigType(nonopt)
        assert nonopt_type.name == 'nonopt'
        assert nonopt_type.types == {'one': 'str', 'two': 'str'}
        assert nonopt_type.required == ('one', 'two')
        assert nonopt_type.positional == ('one', 'two')

    def test_default_types(self):
        test_type = basics.ConfigType(alltypes)
        assert test_type.types == {
            'alist': 'list', 'astr': 'str', 'abool': 'bool',
            'anint': 'int', 'along': 'int'}
        assert not test_type.required

    @pytest.mark.parametrize('func', (
        pytest.param(NewStyleClass(1).member, id='newstyle_instance'),
        pytest.param(OldStyleClass(1).member, id='oldstyle_instance'),
        pytest.param(NewStyleClass.member, id='newstyle_class'),
        pytest.param(OldStyleClass.member, id='oldstyle_class'),
    ))
    def test_class_member(self, func):
        test_type = basics.ConfigType(func)
        assert test_type.name == 'member'
        assert test_type.required == ('one',)


class TestConfigTypeFromClass:

    def _test_basics(self, klass, name, two_override=None):
        test_type = basics.ConfigType(klass)
        assert test_type.name == name
        assert set(test_type.required) == {'one'}
        target_types = {'one': 'str'}
        if two_override is not None:
            target_types['two'] = two_override
        assert target_types == test_type.types
        assert test_type.name == name

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
        assert 'interesting' == basics.ConfigType(Class).doc

    def test_object_init(self):
        class kls:
            pass
        conf = basics.ConfigType(kls)
        assert not conf.types
        assert not conf.required

    def test_builtin_targets(self):
        # ensure it's a type error, rather than an attributeerror
        # from not being able to pull func_code
        with pytest.raises(TypeError):
            basics.ConfigType(dict)

    def test_builtin_full_override(self):
        # check our assumptions...
        # and yes, the signatures below are for file rather than
        # dict; we need a cpy class for the test, the ConfigHint doesn't
        # have to be accurate however
        class cls(dict):
            __slots__ = ()
        with pytest.raises(TypeError):
            basics.ConfigType(cls)

        raw_hint = ConfigHint(types={"filename":"str", "mode":"r",
            "buffering":"int"}, typename='file',
            required=['filename'], positional=['filename'])

        # make sure it still tries to introspect, and throws typeerror.
        # introspection is generally wanted- if it must be skipped, the
        # ConfigHint must make it explicit
        cls.pkgcore_config_type = raw_hint
        with pytest.raises(TypeError):
            basics.ConfigType(cls)
        cls.pkgcore_config_type = raw_hint.clone(authorative=True)
        conf = basics.ConfigType(cls)
        assert conf.name == 'file'
        assert list(conf.required) == ['filename']
        assert list(conf.positional) == ['filename']
        assert set(conf.types) == {'buffering', 'filename', 'mode'}

class TestConfigHint:

    def test_configurable_decorator(self):
        @configurable(typename='spork', types={'foon': 'str'})
        def stuff(*args, **kwargs):
            return args, kwargs

        assert 'spork' == stuff.pkgcore_config_type.typename
        assert 'str' == basics.ConfigType(stuff).types['foon']
        assert (('spork',), {}) == stuff('spork')


    def test_clone(self):
        c = ConfigHint(types={'foo': 'list', 'one': 'str'},
            positional=['one'], required=['one'],
            typename='barn', doc='orig doc')
        c2 = c.clone(types={'foo': 'list', 'one': 'str', 'two': 'str'},
            required=['one', 'two'])
        assert c2.types == {'foo': 'list', 'one': 'str', 'two': 'str'}
        assert c2.positional == c.positional
        assert c2.required == ['one', 'two']
        assert c2.typename == c.typename
        assert c2.allow_unknowns == c.allow_unknowns
        assert c2.doc == c.doc

class TestConfigSection:

    def test_section_ref_collapse(self):
        # Silly testcase just to make something drop off the --coverage radar.
        ref = basics.LazySectionRef(None, 'ref:foon')
        pytest.raises(NotImplementedError, ref._collapse)
        pytest.raises(NotImplementedError, ref.collapse)
        pytest.raises(NotImplementedError, ref.instantiate)

    def test_basics(self):
        section = basics.ConfigSection()
        pytest.raises(NotImplementedError, section.__contains__, 42)
        pytest.raises(NotImplementedError, section.keys)
        pytest.raises(NotImplementedError, section.render_value, None, 'a', 'str')


class TestDictConfigSection:

    def test_misc(self):
        def convert(central, value, arg_type):
            return central, value, arg_type
        section = basics.DictConfigSection(convert, {'list': [1, 2]})
        assert 'foo' not in section
        assert 'list' in section
        assert ['list'] == list(section.keys())
        assert (None, [1, 2], 'spoon') == section.render_value(None, 'list', 'spoon')

    def test_failure(self):
        def fail(central, value, arg_type):
            raise errors.ConfigurationError('fail')
        section = basics.DictConfigSection(fail, {'list': [1, 2]})
        with pytest.raises(errors.ConfigurationError):
            section.render_value(None, 'list', 'spoon')


class TestFakeIncrementalDictConfigSection:

    @staticmethod
    def _convert(central, value, arg_type):
        return central, value, arg_type

    @staticmethod
    def _fail(central, value, arg_type):
        raise errors.ConfigurationError('fail')

    def test_misc(self):
        section = basics.FakeIncrementalDictConfigSection(
            self._convert, {'list': [1, 2]})
        assert 'foo' not in section
        assert 'list' in section
        assert ['list'] == list(section.keys())
        with pytest.raises(errors.ConfigurationError):
            obj = basics.FakeIncrementalDictConfigSection(self._fail, {'a': 'b'})
            obj.render_value(None, 'a', 'str')

    def test_fake_incrementals(self):
        section = basics.FakeIncrementalDictConfigSection(
            self._convert, {'seq.append': [1, 2]})
        manager = object()
        assert [None, None, (manager, [1, 2], 'list')] == section.render_value(manager, 'seq', 'list')
        def _repr(central, value, arg_type):
            return 'list', ['thing']
        section = basics.FakeIncrementalDictConfigSection(
            _repr, {'foo': None})
        assert ('list', (None, ['thing'], None)) == section.render_value(manager, 'foo', 'repr')
        with pytest.raises(errors.ConfigurationError):
            obj = basics.FakeIncrementalDictConfigSection(self._fail, {'a.prepend': 'b'})
            obj.render_value(None, 'a', 'list')

    def test_repr(self):
        def asis(central, value, arg_type):
            assert arg_type == 'repr', arg_type
            return value
        source_dict = {
            'seq.append': ('list', [1, 2]),
            'simple': ('bool', True),
            'multistr': ('str', 'body'),
            'multistr.prepend': ('str', 'head'),
            'refs': ('str', 'lost'),
            'refs.append': ('ref', 'main'),
            'refs.prepend': ('refs', ['a', 'b']),
            'strlist': ('callable', asis),
            'strlist.prepend': ('str', 'whatever'),
            'wrong.prepend': ('wrong', 'wrong'),
        }
        section = basics.FakeIncrementalDictConfigSection(asis, source_dict)
        manager = object()
        with pytest.raises(KeyError):
            section.render_value(manager, 'spoon', 'repr')
        assert ('list', [None, None, [1, 2]]) == section.render_value(manager, 'seq', 'repr')
        assert ('bool', True) == section.render_value(manager, 'simple', 'repr')
        assert ('str', ['head', 'body', None]) == section.render_value(manager, 'multistr', 'repr')
        assert ('refs', [['a', 'b'], ['lost'], ['main']]) == section.render_value(manager, 'refs', 'repr')
        assert ('list', [
                    ['whatever'],
                    ['tests.config.test_basics.asis'],
                    None]) == section.render_value(manager, 'strlist', 'repr')
        with pytest.raises(errors.ConfigurationError):
            section.render_value(manager, 'wrong', 'repr')


class TestConvertString:

    def test_render_value(self):
        source = {
            'str': 'tests',
            'bool': 'yes',
            'list': '0 1 2',
            'callable': 'tests.config.test_basics.passthrough',
        }
        destination = {
            'str': 'tests',
            'bool': True,
            'list': ['0', '1', '2'],
            'callable': passthrough,
        }

        # valid gets
        for typename, value in destination.items():
            assert value == basics.convert_string(None, source[typename], typename)

        # reprs
        for typename, value in source.items():
            assert ('str', value) == basics.convert_string(None, source[typename], 'repr')
        # invalid gets
        # not callable
        with pytest.raises(errors.ConfigurationError):
            basics.convert_string(None, source['str'], 'callable')
        # not importable
        with pytest.raises(errors.ConfigurationError):
            basics.convert_string(None, source['bool'], 'callable')
        # Bogus type.
        with pytest.raises(errors.ConfigurationError):
            basics.convert_string(None, source['bool'], 'frob')

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
        assert basics.convert_string(TestCentral(), 'target', 'ref:spoon').collapse() == target_config
        with pytest.raises(errors.ConfigurationError):
            basics.convert_string(TestCentral(), 'missing', 'ref:spoon').instantiate()

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
        assert [config1, config2] == list(ref.collapse() for ref in basics.convert_string(
                    TestCentral(), '1 2', 'refs:spoon'))
        lazy_refs = basics.convert_string(TestCentral(), '2 3', 'refs:spoon')
        assert len(lazy_refs) == 2
        with pytest.raises(errors.ConfigurationError):
            lazy_refs[1].collapse()


class TestConvertAsIs:

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
                    assert value == basics.convert_asis(None, value, typename)
                else:
                    with pytest.raises(errors.ConfigurationError):
                        basics.convert_asis(None, value, typename)

    def test_repr(self):
        for typename, value in self.source.items():
            assert (typename, value) == basics.convert_asis(None, value, 'repr')
        with pytest.raises(errors.ConfigurationError):
            basics.convert_asis(None, object(), 'repr')

    def test_section_ref(self):
        ref = basics.HardCodedConfigSection({})
        with pytest.raises(errors.ConfigurationError):
            basics.convert_asis(None, 42, 'ref:spoon')
        assert ref is basics.convert_asis(None, ref, 'ref:spoon').section
        assert ('ref', ref) == basics.convert_asis(None, ref, 'repr')

    def test_section_refs(self):
        ref = basics.HardCodedConfigSection({})
        with pytest.raises(errors.ConfigurationError):
            basics.convert_asis(None, [1, 2], 'refs:spoon')
        assert ref is basics.convert_asis(None, [ref], 'refs:spoon')[0].section
        assert ('refs', [ref]) == basics.convert_asis(None, [ref], 'repr')


def test_alias():
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
    assert 'spoon' == type_obj.name
    assert foon is alias.render_value(manager, 'target', 'ref:spoon').collapse()


class TestParsers:

    def test_str_to_bool(self):
        # abuse assert is to make sure we get actual booleans, not some
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
            assert basics.str_to_bool(string) is output

    def test_str_to_int(self):
        for string, output in [
            ('\t 1', 1),
            ('1', 1),
            ('-100', -100)]:
            assert basics.str_to_int(string) == output
        with pytest.raises(errors.ConfigurationError):
            basics.str_to_int('f')

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
            assert basics.str_to_str(string) == output

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
            assert basics.str_to_list(string) == output
        for string in ['"', "'foo", 'ba"r', 'baz"']:
            with pytest.raises(errors.QuoteInterpretationError):
                basics.str_to_list(string)
        # make sure this explodes instead of returning something
        # confusing so we explode much later
        with pytest.raises(TypeError):
            basics.str_to_list(['no', 'string'])


def test_parse_config_file(tmp_path):
    (fp := tmp_path / 'file').write_text('foon')
    with pytest.raises(errors.ConfigurationError):
        basics.parse_config_file('/spork', None)
    def parser(f):
        return f.read()
    assert 'foon' == basics.parse_config_file(fp, parser)
