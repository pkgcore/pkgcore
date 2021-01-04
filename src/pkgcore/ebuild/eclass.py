"""Eclass parsing support."""

import os
import re
import shlex
import subprocess

from snakeoil import klass
from snakeoil.mappings import ImmutableDict, OrderedSet
from snakeoil.strings import pluralism

from . import conditionals
from .eapi import EAPI


class EclassDocParsingError(Exception):
    """Error when parsing eclass docs."""


class AttrDict(ImmutableDict):
    """Support accessing dict keys as attributes."""

    def __getattr__(self, name):
        try:
            object.__getattribute__(self, name)
        except AttributeError as e:
            try:
                return object.__getattribute__(self, '_dict')[name]
            except KeyError:
                raise e

    def __dir__(self):
        return sorted(dir(self._dict) + list(self._dict))


class ParseEclassDoc:
    """Generic block for eclass docs.

    See the devmanual [#]_ for the eclass docs specification.

    .. [#] https://devmanual.gentoo.org/eclass-writing/#documenting-eclasses
    """

    # block tag
    tag = None
    # block key name -- None for singular block types
    key = None
    # boolean flagging if block attribute defaults should be inserted
    default = False

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
        # regex matching @CODE tags for literal blocks
        self._code_block = re.compile(r'^\s*@CODE\s*$')

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

    def _tag_multiline_args(self, block, tag, lineno):
        """Parse tags with multiline arguments."""
        if block[0]:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: invalid inline arg')
        if not block[1:]:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: missing args')
        return tuple(block[1:])

    def _tag_multiline_str(self, block, tag, lineno):
        """Parse tags with multiline text while handling @CODE tags."""
        lines = list(self._tag_multiline_args(block, tag, lineno))
        # drop extra blank newlines
        for line in reversed(lines):
            if line:
                break
            lines.pop()

        data = []
        code_block = False
        for i, line in enumerate(lines, 1):
            if self._code_block.match(line):
                # in a literal code block
                if code_block:
                    code_block = False
                else:
                    code_block = lineno + i
                    data.extend(['\n', '.. code-block:: bash', '\n\n'])
            elif line:
                if code_block:
                    # add indentation for code blocks
                    line = f'  {line}'
                elif line.lstrip() != line:
                    raise EclassDocParsingError(
                        f'{repr(tag)}, line {lineno + i}: indented code not in @CODE block')
                data.append(f'{line}\n')
            else:
                data.append('\n')

        if code_block:
            raise EclassDocParsingError(f'{repr(tag)}, line {code_block}: unterminated @CODE block')

        return ''.join(data)

    def _tag_deprecated(self, block, tag, lineno):
        """Parse deprecated tags."""
        arg = self._tag_inline_arg(block, tag, lineno)
        return True if arg.lower() == 'none' else arg

    @klass.jit_attr
    def _required(self):
        """Set of required eclass doc block tags."""
        tags = set()
        for tag, (_name, required, _func, _default) in self.tags.items():
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

    @property
    def defaults(self):
        """Return default field mapping for the block."""
        return {name: default for name, _required, _func, default in self.tags.values()}

    def parse(self, lines, line_ind):
        """Parse an eclass block."""
        blocks = []
        data = self.defaults
        # track if all required tags are defined
        missing_tags = set(self._required)

        # split eclass doc block into separate blocks by tag
        for i, line in enumerate(lines):
            if (mo := self._block_tags_re.match(line)):
                tag = mo.group('tag')
                missing_tags.discard(tag)
                value = mo.group('value').strip()
                blocks.append((tag, line_ind + i, [value]))
            else:
                blocks[-1][-1].append(line)

        # parse each tag block
        for tag, line_ind, block in blocks:
            name, required, func, _default = self.tags[tag]
            data[name] = func(block, tag, line_ind)

        # check if any required tags are missing
        if missing_tags:
            missing_tags_str = ', '.join(map(repr, missing_tags))
            s = pluralism(missing_tags)
            raise EclassDocParsingError(
                f'{repr(lines[0])}: missing tag{s}: {missing_tags_str}')

        return AttrDict(data)


class EclassBlock(ParseEclassDoc):
    """ECLASS doc block."""

    tag = '@ECLASS:'

    def __init__(self):
        tags = {
            '@ECLASS:': ('name', True, self._tag_inline_arg, None),
            '@VCSURL:': ('vcsurl', False, self._tag_inline_arg, None),
            '@BLURB:': ('blurb', True, self._tag_inline_arg, None),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated, False),
            '@INDIRECT_ECLASSES:': ('indirect_eclasses', False, self._tag_inline_list, ()),
            '@MAINTAINER:': ('maintainers', True, self._tag_multiline_args, None),
            '@AUTHOR:': ('authors', False, self._tag_multiline_args, None),
            '@BUGREPORTS:': ('bugreports', False, self._tag_multiline_str, None),
            '@DESCRIPTION:': ('description', False, self._tag_multiline_str, None),
            '@EXAMPLE:': ('example', False, self._tag_multiline_str, None),
            '@SUPPORTED_EAPIS:': ('supported_eapis', False, self._supported_eapis, ()),
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
        return OrderedSet(eapis)


class EclassVarBlock(ParseEclassDoc):
    """ECLASS-VARIABLE doc block."""

    tag = '@ECLASS-VARIABLE:'
    key = 'variables'
    default = True

    def __init__(self):
        tags = {
            '@ECLASS-VARIABLE:': ('name', True, self._tag_inline_arg, None),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated, False),
            '@DEFAULT_UNSET': ('default_unset', False, self._tag_bool, False),
            '@INTERNAL': ('internal', False, self._tag_bool, False),
            '@REQUIRED': ('required', False, self._tag_bool, False),
            '@PRE_INHERIT': ('pre_inherit', False, self._tag_bool, False),
            '@USER_VARIABLE': ('user_variable', False, self._tag_bool, False),
            '@OUTPUT_VARIABLE': ('output_variable', False, self._tag_bool, False),
            '@DESCRIPTION:': ('description', True, self._tag_multiline_str, None),
        }
        super().__init__(tags)


class EclassFuncBlock(ParseEclassDoc):
    """FUNCTION doc block."""

    tag = '@FUNCTION:'
    key = 'functions'
    default = True

    def __init__(self):
        tags = {
            '@FUNCTION:': ('name', True, self._tag_inline_arg, None),
            '@RETURN:': ('returns', False, self._tag_inline_arg, None),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated, False),
            '@INTERNAL': ('internal', False, self._tag_bool, False),
            '@MAINTAINER:': ('maintainers', False, self._tag_multiline_args, None),
            '@DESCRIPTION:': ('description', False, self._tag_multiline_str, None),
            # TODO: The devmanual states this is required, but disabling for now since
            # many phase override functions don't document usage.
            '@USAGE:': ('usage', False, self._usage, None),
        }
        super().__init__(tags)

    def _usage(self, block, tag, lineno):
        """Parse @USAGE tag arguments.

        Empty usage is allowed for functions with no arguments.
        """
        if len(block) > 1:
            raise EclassDocParsingError(f'{repr(tag)}, line {lineno}: non-inline arg')
        return block[0]

    def parse(self, *args):
        data = super().parse(*args)
        if not (data.returns or data.description):
            raise EclassDocParsingError(f'{repr(self.tag)}, @RETURN or @DESCRIPTION required')
        return data


class EclassFuncVarBlock(ParseEclassDoc):
    """VARIABLE doc block."""

    tag = '@VARIABLE:'
    key = 'function_variables'
    default = True

    def __init__(self):
        tags = {
            '@VARIABLE:': ('name', True, self._tag_inline_arg, None),
            '@DEPRECATED:': ('deprecated', False, self._tag_deprecated, False),
            '@DEFAULT_UNSET': ('default_unset', False, self._tag_bool, False),
            '@INTERNAL': ('internal', False, self._tag_bool, False),
            '@REQUIRED': ('required', False, self._tag_bool, False),
            '@DESCRIPTION:': ('description', True, self._tag_multiline_str, None),
        }
        super().__init__(tags)


_eclass_blocks_re = re.compile(
    rf'^(?P<prefix>\s*#) (?P<tag>{"|".join(ParseEclassDoc.blocks)})(?P<value>.*)')


class EclassDoc(AttrDict):
    """Support parsing eclass docs for a given eclass path."""

    def __init__(self, path, /, *, sourced=False, error_callback=None):
        self.mtime = os.path.getmtime(path)

        # set default fields
        data = {}
        data.update(ParseEclassDoc.blocks['@ECLASS:'].defaults)
        for block_obj in ParseEclassDoc.blocks.values():
            if block_obj.default:
                data[block_obj.key] = OrderedSet()

        try:
            data.update(self.parse(path))
        except EclassDocParsingError as e:
            # parse errors are ignored by default
            if error_callback is not None:
                error_callback(e)

        # inject full lists of exported funcs and vars
        if sourced:
            data.update(self._source_eclass(path))

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
    def function_names(self):
        """Set of documented function names in the eclass."""
        return frozenset(x.name for x in self.functions)

    @property
    def internal_function_names(self):
        """Set of internal function names in the eclass."""
        # include all internal tagged functions
        s = {x.name for x in self.functions if x.internal}
        # and all exported, underscore-prefixed functions
        s.update(x for x in self._dict.get('_exported_funcs', ()) if x.startswith('_'))
        return frozenset(s)

    @property
    def exported_function_names(self):
        """Set of all exported function names in the eclass."""
        return frozenset(self._dict.get('_exported_funcs', ()))

    @property
    def variable_names(self):
        """Set of documented variable names in the eclass."""
        return frozenset(x.name for x in self.variables)

    @property
    def internal_variable_names(self):
        """Set of internal variable names in the eclass."""
        # include all internal tagged variables
        s = {x.name for x in self.variables if x.internal}
        # and all exported, underscore-prefixed variables
        s.update(x for x in self._dict.get('_exported_vars', ()) if x.startswith('_'))
        return frozenset(s)

    @property
    def exported_variable_names(self):
        """Set of all exported variable names in the eclass.

        Ignores variables that start with underscores since
        it's assumed they are private.
        """
        return frozenset(self._dict.get('_exported_vars', ()))

    @property
    def function_variable_names(self):
        """Set of documented function variable names in the eclass."""
        return frozenset(x.name for x in self.function_variables)

    @property
    def live(self):
        """Eclass implements functionality to support a version control system."""
        return 'live' in self._dict.get('_properties', ())

    @staticmethod
    def parse(path):
        """Parse eclass docs."""
        blocks = []

        with open(path) as f:
            lines = f.read().splitlines()
            line_ind = 0

            while line_ind < len(lines):
                if (mo := _eclass_blocks_re.match(lines[line_ind])):
                    # Isolate identified doc block by pulling all following
                    # lines with a matching prefix.
                    prefix = mo.group('prefix')
                    tag = mo.group('tag')
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
            raise EclassDocParsingError("'@ECLASS:' block missing")
        elif blocks[0][0] != '@ECLASS:':
            raise EclassDocParsingError("'@ECLASS:' block not first")

        data = {block.key: OrderedSet() for block in ParseEclassDoc.blocks.values() if block.default}
        duplicates = {k: set() for k in ParseEclassDoc.blocks}

        # parse identified blocks
        for tag, block, block_start in blocks:
            block_obj = ParseEclassDoc.blocks[tag]
            block_data = block_obj.parse(block, block_start)
            # check if duplicate blocks exist and merge data
            if block_obj.key is None:
                if block_data.keys() & data.keys():
                    raise EclassDocParsingError(
                        f"'@ECLASS:', line {block_start}: duplicate block")
                # verify name is correct
                file_name = os.path.basename(path)
                if block_data.name != file_name:
                    raise EclassDocParsingError(
                        f"'@ECLASS:' invalid name {block_data.name!r} (should be {file_name!r})")
                data.update(block_data)
            else:
                name = block_data['name']
                if name in duplicates[tag]:
                    raise EclassDocParsingError(
                        f'{repr(block[0])}, line {block_start}: duplicate block')
                duplicates[tag].add(name)
                data[block_obj.key].add(block_data)

        return data
