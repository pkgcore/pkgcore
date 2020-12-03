"""Eclass parsing support."""

from collections import UserDict
import os
import re
import shlex
import subprocess

from pkgcore.ebuild import conditionals
from pkgcore.ebuild.eapi import EAPI
from snakeoil import klass
from snakeoil.strings import pluralism


class EclassDocParsingError(Exception):
    """Error when parsing eclass docs."""


def _parsing_error(exc):
    """Callback to handle parsing exceptions."""
    raise exc


class ParseEclassDoc:
    """Generic block for eclass docs.

    See the devmanual [#]_ for the eclass docs specification.

    .. [#] https://devmanual.gentoo.org/eclass-writing/#documenting-eclasses
    """

    # block tag
    tag = None
    # block key name -- None for singular block types
    key = None

    # mapping from eclass doc blocks to parsing instances
    blocks = {}

    def __init_subclass__(cls, **kwargs):
        """Register known eclass doc block tags."""
        super().__init_subclass__(**kwargs)
        cls.blocks[cls.tag] = cls()

    def __init__(self, tags):
        self.tags = tags
        # regex matching all known tags for the eclass doc block
        self._block_tags_re = re.compile(rf'^(?P<tag>{"|".join(self.tags)})(?P<value>.*)')

    def _tag_bool(self, block, tag, lineno):
        """Parse boolean tags."""
        try:
            args = next(x for x in block if x)
            raise EclassDocParsingError(
                f'{repr(tag)}, line {lineno}: tag takes no args, got {repr(args)}')
        except StopIteration:
            pass
        return True

    def _tag_inline_arg(self, block, tag, lineno):
        """Parse tags with inline argument."""
        if not block[0]:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: missing inline arg')
        elif len(block) > 1:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: non-inline arg')
        return block[0]

    def _tag_inline_list(self, block, tag, lineno):
        """Parse tags with inline, space-separated list argument."""
        line = self._tag_inline_arg(block, tag, lineno)
        return tuple(line.split())

    # TODO: add support for @CODE blocks once doc output is added
    def _tag_multiline_args(self, block, tag, lineno):
        """Parse tags with multiline arguments."""
        if block[0]:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: invalid inline arg')
        if not block[1:]:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: missing args')
        return tuple(block[1:])

    def _tag_deprecated(self, block, tag, lineno):
        """Parse deprecated tags."""
        arg = self._tag_inline_arg(block, tag, lineno)
        return None if arg.lower() == 'none' else arg

    @klass.jit_attr
    def _required(self):
        """Set of required eclass doc block tags."""
        tags = set()
        for tag, (_name, required, _func) in self.tags.items():
            if required:
                tags.add(tag)
        return frozenset(tags)

    @klass.jit_attr
    def bash_env_vars(self):
        """The set of all bash variables defined in the default environment."""
        variables = []
        # use no-op to fake a pipeline so pipeline specific vars are defined
        p = subprocess.run(
            ['bash', '-c', ':; compgen -A variable'],
            stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding='utf8')
        if p.returncode == 0:
            variables = p.stdout.splitlines()
        return frozenset(variables)

    def parse(self, lines, line_ind):
        """Parse an eclass block."""
        blocks = []
        data = dict()
        # track if all required tags are defined
        missing_tags = set(self._required)

        # split eclass doc block into separate blocks by tag
        for i, line in enumerate(lines):
            m = self._block_tags_re.match(line)
            if m is not None:
                tag = m.group('tag')
                missing_tags.discard(tag)
                value = m.group('value').strip()
                blocks.append((tag, line_ind + i, [value]))
            else:
                blocks[-1][-1].append(line)

        # parse each tag block
        for tag, line_ind, block in blocks:
            name, required, func = self.tags[tag]
            try:
                data[name] = func(block, tag, line_ind)
            except EclassDocParsingError as e:
                _parsing_error(e)

        # check if any required tags are missing
        if missing_tags:
            missing_tags_str = ', '.join(map(repr, missing_tags))
            s = pluralism(missing_tags)
            _parsing_error(EclassDocParsingError(
                f'{repr(lines[0])}: missing tag{s}: {missing_tags_str}'))

        return data


class EclassBlock(ParseEclassDoc):
    """ECLASS doc block."""

    tag = '@ECLASS:'

    def __init__(self):
        tags = {
            '@ECLASS:': ('name', True, self._tag_inline_arg),
            '@VCSURL:': ('vcsurl', False, self._tag_inline_arg),
            '@BLURB:': ('blurb', True, self._tag_inline_arg),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated),
            '@INDIRECT_ECLASSES:': ('indirect_eclasses', False, self._tag_inline_list),

            '@MAINTAINER:': ('maintainers', True, self._tag_multiline_args),
            '@AUTHOR:': ('authors', False, self._tag_multiline_args),
            '@BUGREPORTS:': ('bugreports', False, self._tag_multiline_args),
            '@DESCRIPTION:': ('description', False, self._tag_multiline_args),
            '@EXAMPLE:': ('example', False, self._tag_multiline_args),

            '@SUPPORTED_EAPIS:': ('supported_eapis', False, self._supported_eapis),
        }
        super().__init__(tags)

        self._known_eapis = frozenset(EAPI.known_eapis)

    def _supported_eapis(self, block, tag, lineno):
        """Parse @SUPPORTED_EAPIS tag arguments."""
        eapis = self._tag_inline_list(block, tag, lineno)
        unknown = set(eapis) - self._known_eapis
        if unknown:
            s = pluralism(unknown)
            unknown_str = ' '.join(sorted(unknown))
            raise EclassDocParsingError(
                f'{repr(tag)}, line {lineno}: unknown EAPI{s}: {unknown_str}')
        return frozenset(eapis)


class EclassVarBlock(ParseEclassDoc):
    """ECLASS-VARIABLE doc block."""

    tag = '@ECLASS-VARIABLE:'
    key = 'variables'

    def __init__(self):
        tags = {
            '@ECLASS-VARIABLE:': ('name', True, self._tag_inline_arg),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated),

            '@DEFAULT_UNSET': ('default_unset', False, self._tag_bool),
            '@INTERNAL': ('internal', False, self._tag_bool),
            '@REQUIRED': ('required', False, self._tag_bool),

            '@PRE_INHERIT': ('pre_inherit', False, self._tag_bool),
            '@USER_VARIABLE': ('user_variable', False, self._tag_bool),
            '@OUTPUT_VARIABLE': ('output_variable', False, self._tag_bool),

            '@DESCRIPTION:': ('description', True, self._tag_multiline_args),
        }
        super().__init__(tags)


class EclassFuncBlock(ParseEclassDoc):
    """FUNCTION doc block."""

    tag = '@FUNCTION:'
    key = 'functions'

    def __init__(self):
        tags = {
            '@FUNCTION:': ('name', True, self._tag_inline_arg),
            '@RETURN:': ('returns', False, self._tag_inline_arg),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated),

            '@INTERNAL': ('internal', False, self._tag_bool),

            '@MAINTAINER:': ('maintainers', False, self._tag_multiline_args),
            '@DESCRIPTION:': ('description', False, self._tag_multiline_args),

            # TODO: The devmanual states this is required, but disabling for now since
            # many phase override functions don't document usage.
            '@USAGE:': ('usage', False, self._usage),
        }
        super().__init__(tags)

    def _usage(self, block, tag, lineno):
        """Parse @USAGE tag arguments.

        Empty usage is allowed for functions with no arguments.
        """
        if len(block) > 1:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: non-inline arg')
        return block[0]


class EclassFuncVarBlock(ParseEclassDoc):
    """VARIABLE doc block."""

    tag = '@VARIABLE:'
    key = 'function-variables'

    def __init__(self):
        tags = {
            '@VARIABLE:': ('name', True, self._tag_inline_arg),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated),

            '@DEFAULT_UNSET': ('default_unset', False, self._tag_bool),
            '@INTERNAL': ('internal', False, self._tag_bool),
            '@REQUIRED': ('required', False, self._tag_bool),

            '@DESCRIPTION:': ('description', True, self._tag_multiline_args),
        }
        super().__init__(tags)


_eclass_blocks_re = re.compile(
    rf'^(?P<prefix>\s*#) (?P<tag>{"|".join(ParseEclassDoc.blocks)})(?P<value>.*)')


class EclassDoc(UserDict):
    """Support parsing eclass docs for a given eclass path."""

    def __init__(self, path, sourced=False):
        self.path = path
        self.mtime = os.path.getmtime(self.path)
        data = {}

        # ignore parsing errors when constructing cache objects
        try:
            data.update(self.parse(self.path))
        except EclassDocParsingError:
            data['_parse_failed'] = True

        # inject full lists of exported funcs and vars
        if sourced:
            data.update(self._source_eclass(self.path))

        super().__init__(data)

    @staticmethod
    def _source_eclass(path):
        data = {}
        # TODO: support this via pkgcore's ebd
        # source eclass to determine PROPERTIES
        p = subprocess.run(
            ['bash', '-c',
                f'source {shlex.quote(path)}; '
                f'compgen -A function; '
                f'echo "#"; '
                f'compgen -A variable; '
                f'echo "#"; '
                f'echo ${{PROPERTIES}}'],
            stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding='utf8')
        if p.returncode == 0:
            eclass_obj = ParseEclassDoc.blocks['@ECLASS:']
            funcs, variables, properties = p.stdout.split('#\n')
            data['_exported_funcs'] = tuple(funcs.split())
            data['_exported_vars'] = tuple(
                x for x in variables.split()
                if x not in eclass_obj.bash_env_vars
            )
            data['_properties'] = conditionals.DepSet.parse(
                properties, str, operators={}, attr='PROPERTIES')
        return data

    @property
    def functions(self):
        """Set of documented function names in the eclass."""
        return frozenset(d['name'] for d in self.data.get('functions', ()))

    @property
    def internal_functions(self):
        """Set of documented internal function names in the eclass."""
        return frozenset(
            d['name'] for d in self.data.get('functions', ())
            if d.get('internal', False)
        )

    @property
    def exported_functions(self):
        """Set of all exported function names in the eclass.

        Ignores functions that start with underscores since
        it's assumed they are private.
        """
        return frozenset(
            x for x in self.data.get('_exported_funcs', ())
            if not x.startswith('_')
        )

    @property
    def variables(self):
        """Set of documented variable names in the eclass."""
        return frozenset(d['name'] for d in self.data.get('variables', ()))

    @property
    def internal_variables(self):
        """Set of documented internal variable names in the eclass."""
        return frozenset(
            d['name'] for d in self.data.get('variables', ())
            if d.get('internal', False)
        )

    @property
    def exported_variables(self):
        """Set of all exported variable names in the eclass.

        Ignores variables that start with underscores since
        it's assumed they are private.
        """
        return frozenset(
            x for x in self.data.get('_exported_vars', ())
            if not x.startswith('_')
        )

    @property
    def indirect_eclasses(self):
        """Set of allowed indirect eclass inherits."""
        return frozenset(self.data.get('indirect_eclasses', ()))

    @property
    def live(self):
        """Eclass implements functionality to support a version control system."""
        return 'live' in self.data.get('_properties', ())

    @staticmethod
    def parse(path):
        """Parse eclass docs."""
        blocks = []

        with open(path) as f:
            lines = f.read().splitlines()
            line_ind = 0

            while line_ind < len(lines):
                m = _eclass_blocks_re.match(lines[line_ind])
                if m is not None:
                    # Isolate identified doc block by pulling all following
                    # lines with a matching prefix.
                    prefix = m.group('prefix')
                    tag = m.group('tag')
                    block = []
                    block_start = line_ind + 1
                    while line_ind < len(lines):
                        line = lines[line_ind]
                        if not line.startswith(prefix):
                            break
                        line = line[len(prefix) + 1:]
                        block.append(line)
                        line_ind += 1
                    blocks.append((tag, block, block_start))
                line_ind += 1

        # @ECLASS block must exist and be first in eclasses
        if not blocks:
            _parsing_error(EclassDocParsingError("'@ECLASS:' block missing"))
        elif blocks[0][0] != '@ECLASS:':
            _parsing_error(EclassDocParsingError("'@ECLASS:' block not first"))

        data = {}
        duplicates = {k: set() for k in ParseEclassDoc.blocks}

        # parse identified blocks
        for tag, block, block_start in blocks:
            block_obj = ParseEclassDoc.blocks[tag]
            block_data = block_obj.parse(block, block_start)
            # check if duplicate blocks exist and merge data
            if block_obj.key is None:
                if block_data.keys() & data.keys():
                    _parsing_error(EclassDocParsingError(
                        f"'@ECLASS:', line {block_start}: duplicate block"))
                data.update(block_data)
            else:
                name = block_data['name']
                if name in duplicates[tag]:
                    _parsing_error(EclassDocParsingError(
                        f'{repr(block[0])}, line {block_start}: duplicate block'))
                duplicates[tag].add(name)
                data.setdefault(block_obj.key, []).append(block_data)

        return data
