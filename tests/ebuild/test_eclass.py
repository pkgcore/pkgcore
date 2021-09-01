from pkgcore.ebuild import eclass
from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import TempDirMixin


class FakeEclass:
    def __init__(self, path, contents):
        self.path = path
        with open(path, 'w') as f:
            f.write(contents)


class FakeEclassCache:
    def __init__(self, temp_dir, eclasses):
        self.eclasses = dict((name, FakeEclass(name, contents))
                             for name, contents in eclasses.items())

    def get_eclass(self, name):
        return self.eclasses.get(name)


class FakeEclassRepo:
    def __init__(self, temp_dir, eclasses):
        self.eclass_cache = FakeEclassCache(temp_dir, eclasses)


def make_eclass(name, provides=None):
    eclass = f'# @ECLASS: {name}.eclass\n'
    if provides is not None:
        eclass += f'# @PROVIDES: {provides}\n'
    return eclass


FOO_ECLASS = '''
# @ECLASS: foo.eclass
# @MAINTAINER:
# Random Person <maintainer@random.email>
# @AUTHOR:
# Another Person <another@random.email>
# Random Person <maintainer@random.email>
# @BUGREPORTS:
# Report bugs somewhere.
# @VCSURL: https://example.com/foo.eclass
# @SUPPORTED_EAPIS: 0 1 2 3 4 5 6 7
# @PROVIDES: bar
# @BLURB: Test eclass.
# @DEPRECATED: bar or frobnicate
# @DESCRIPTION:
# Yadda yadda yadda.
# Lots to say here.
#
# Really, very interesting eclass.
#
# @SUBSECTION How to use it
# Somehow.
#
# @EXAMPLE:
# @CODE
# inherit foo
#
# src_prepare() {
#   foo_public_func
# }
# @CODE

# @ECLASS-VARIABLE: _FOO_INTERNAL_ECLASS_VAR
# @INTERNAL
# @DEFAULT_UNSET
# @DESCRIPTION:
# Internal variable.

# @ECLASS-VARIABLE: FOO_PUBLIC_ECLASS_VAR
# @PRE_INHERIT
# @REQUIRED
# @DEPRECATED: BAR_PUBLIC_ECLASS_VAR
# @DESCRIPTION:
# Public variable.

# @FUNCTION: _foo_internal_func
# @USAGE: <bar> [<baz>]
# @RETURN: nothing special
# @MAINTAINER:
# Some Person <someone@random.email>
# @INTERNAL
# @DESCRIPTION:
# Internal stub function.
_foo_internal_func() { :; }

# @VARIABLE: _FOO_INTERNAL_VAR
# @INTERNAL
# @DEFAULT_UNSET
# @DESCRIPTION:
# Internal variable for foo_public_func.

# @VARIABLE: FOO_PUBLIC_VAR
# @REQUIRED
# @DEPRECATED: BAR_PUBLIC_VAR
# @DESCRIPTION:
# Public variable for foo_public_func.

# @FUNCTION: foo_public_func
# @DEPRECATED: bar_public_func
# @DESCRIPTION:
# Public stub function.
foo_public_func() { :; }
'''


class TestEclassDoc(TempDirMixin, TestCase):
    def test_foo_eclass(self):
        with open(pjoin(self.dir, 'foo.eclass'), 'w') as f:
            f.write(FOO_ECLASS)
        doc = eclass.EclassDoc(pjoin(self.dir, 'foo.eclass'))
        assert doc.name == 'foo.eclass'
        assert doc.vcsurl == 'https://example.com/foo.eclass'
        assert doc.blurb == 'Test eclass.'
        assert doc.deprecated == 'bar or frobnicate'
        assert doc.raw_provides == ('bar',)
        assert doc.maintainers == ('Random Person <maintainer@random.email>',)
        assert doc.authors == ('Another Person <another@random.email>',
                               'Random Person <maintainer@random.email>',)
        assert doc.bugreports == '::\n\n  Report bugs somewhere.'
        assert doc.description == ('::\n\n'
                                   '  Yadda yadda yadda.\n'
                                   '  Lots to say here.\n\n'
                                   '  Really, very interesting eclass.\n\n'
                                   'How to use it\n'
                                   '~~~~~~~~~~~~~\n'
                                   '::\n\n'
                                   '  Somehow.')
        assert doc.example == ('::\n\n'
                               '  inherit foo\n\n'
                               '  src_prepare() {\n'
                               '    foo_public_func\n'
                               '  }')
        assert doc.supported_eapis == frozenset(map(str, range(8)))

        assert doc.function_names == frozenset(('_foo_internal_func', 'foo_public_func'))
        assert doc.internal_function_names == frozenset(('_foo_internal_func',))

        assert doc.function_variable_names == frozenset(('FOO_PUBLIC_VAR', '_FOO_INTERNAL_VAR'))

        assert doc.variable_names == frozenset(('FOO_PUBLIC_ECLASS_VAR', '_FOO_INTERNAL_ECLASS_VAR'))
        assert doc.internal_variable_names == frozenset(('_FOO_INTERNAL_ECLASS_VAR',))

        assert len(doc.functions) == 2
        assert doc.functions[0] == {'name': '_foo_internal_func',
                                    'returns': 'nothing special',
                                    'deprecated': False,
                                    'internal': True,
                                    'maintainers': ('Some Person <someone@random.email>',),
                                    'description': '::\n\n  Internal stub function.',
                                    'usage': '<bar> [<baz>]'}

        assert doc.functions[1] == {'name': 'foo_public_func',
                                    'returns': None,
                                    'deprecated': 'bar_public_func',
                                    'internal': False,
                                    'maintainers': None,
                                    'description': '::\n\n  Public stub function.',
                                    'usage': None}

        assert len(doc.function_variables) == 2
        assert doc.function_variables[0] == {'name': '_FOO_INTERNAL_VAR',
                                             'deprecated': False,
                                             'default_unset': True,
                                             'internal': True,
                                             'required': False,
                                             'description': '::\n\n  Internal variable for foo_public_func.'}
        assert doc.function_variables[1] == {'name': 'FOO_PUBLIC_VAR',
                                             'deprecated': 'BAR_PUBLIC_VAR',
                                             'default_unset': False,
                                             'internal': False,
                                             'required': True,
                                             'description': '::\n\n  Public variable for foo_public_func.'}

        assert len(doc.variables) == 2
        assert doc.variables[0] == {'name': '_FOO_INTERNAL_ECLASS_VAR',
                                    'deprecated': False,
                                    'default_unset': True,
                                    'internal': True,
                                    'required': False,
                                    'pre_inherit': False,
                                    'user_variable': False,
                                    'output_variable': False,
                                    'description': '::\n\n  Internal variable.'}
        assert doc.variables[1] == {'name': 'FOO_PUBLIC_ECLASS_VAR',
                                    'deprecated': 'BAR_PUBLIC_ECLASS_VAR',
                                    'default_unset': False,
                                    'internal': False,
                                    'required': True,
                                    'pre_inherit': True,
                                    'user_variable': False,
                                    'output_variable': False,
                                    'description': '::\n\n  Public variable.'}

    def test_recursive_provides(self):
        repo = FakeEclassRepo(self.dir, {
            'foo': FOO_ECLASS,
            'bar': make_eclass('bar', provides='deep1 deep2'),
            'deep1': make_eclass('deep1 deep2'),
            'deep2': make_eclass('deep2 foo'),
        })
        assert (eclass.EclassDoc(repo.eclass_cache.get_eclass('foo').path, repo=repo).provides ==
                {'bar', 'deep1', 'deep2'})
