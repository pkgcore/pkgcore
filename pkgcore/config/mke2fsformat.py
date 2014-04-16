# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Parse a mke2fs.conf(5) style configuration file.

Example of the supported format (not a complete config)::

    # this is a comment.
    # this is a config section.
    [metadata]
        # strings may be quoted or unquoted. semicolon terminator.
        type = cache
        class = pkgcore.cache.metadata.database
        # true, yes or 1 for boolean True (case-insensitive).
        readonly = true
        location = /usr/portage/


    # this needs to be quoted because it has a space in it
    [livefs domain]
        # this could be unquoted.
        type = "domain"
        package.keywords = "/etc/portage/package.keywords"
        default = yes
        # this is a section reference, with a nested anonymous section.
        repositories = {
            type = repo
            class = pkgcore.ebuild.repository.tree
            location = /usr/portage
            # this is also a section reference, but instead of a nested section
            # we refer to the named metadata section above
            cache = metadata
        }
        fetcher = {
            type = fetcher
            distdir = /usr/portage/distfiles
        }
"""

__all__ = ("config_from_file",)

# The tests for this are in test_dhcpformat.

from pkgcore.config import dhcpformat, errors
from snakeoil import mappings
import pyparsing as pyp


_section_contents = pyp.Forward()
_value = (pyp.Word(pyp.alphanums + './_').setWhitespaceChars(' \t') |
          pyp.quotedString.copy().setParseAction(pyp.removeQuotes))

_section = pyp.Group(
    pyp.Suppress('{' + pyp.lineEnd) + _section_contents + pyp.Suppress('}'))

# "statement seems to have no effect"
# pylint: disable-msg=W0104
_section_contents << pyp.dictOf(
    _value + pyp.Suppress('='),
    pyp.Group(pyp.OneOrMore((_value | _section).setWhitespaceChars(' \t'))) +
    pyp.Suppress(pyp.lineEnd))

parser = (
    pyp.stringStart +
    pyp.dictOf(
        pyp.Suppress('[') + _value + pyp.Suppress(']' + pyp.lineEnd),
        _section_contents).ignore(pyp.pythonStyleComment) +
    pyp.stringEnd)


def config_from_file(file_obj):
    try:
        config = parser.parseFile(file_obj)
    except pyp.ParseException as e:
        name = getattr(file_obj, 'name', file_obj)
        raise errors.ConfigurationError('%s: %s' % (name, e))
    def build_section(name):
        return dhcpformat.ConfigSection(config[name])
    return mappings.LazyValDict(config.keys, build_section)
