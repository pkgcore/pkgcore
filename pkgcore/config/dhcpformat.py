# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Parse a dhcpd.conf(5) style configuration file.

Example of the supported format (not a complete config)::

    # this is a comment.
    # this is a config section.
    metadata {
        # strings may be quoted or unquoted. semicolon terminator.
        type cache;
        class pkgcore.cache.metadata.database;
        # true, yes or 1 for boolean True (case-insensitive).
        readonly true;
        location /usr/portage/
    }

    # this needs to be quoted because it has a space in it
    "livefs domain" {
        # this could be unquoted.
        type "domain";
        package.keywords "/etc/portage/package.keywords";
        default yes;
        # this is a section reference, with a nested anonymous section.
        repositories {
            type repo;
            class pkgcore.ebuild.repository.tree;
            location /usr/portage;
            # this is also a section reference, but instead of a nested section
            # we refer to the named metadata section above
            cache metadata;
        };
        fetcher {
            type fetcher;
            distdir /usr/portage/distfiles;
        }
    }
"""

__all__ = ("config_from_file",)

from pkgcore.config import basics, errors
from snakeoil import mappings, modules

import pyparsing as pyp

# this is based on the 'BIND named.conf parser' on pyparsing's webpage

_section = pyp.Forward()
_value = (pyp.Word(pyp.alphanums + './_') |
          pyp.quotedString.copy().setParseAction(pyp.removeQuotes))

_section_contents = pyp.dictOf(
    _value, pyp.Group(pyp.OneOrMore(_value | _section)) + pyp.Suppress(';'))

# "statement seems to have no effect"
# pylint: disable-msg=W0104
_section << pyp.Group(pyp.Suppress('{') + _section_contents +
                      pyp.Suppress('}'))

parser = (
    pyp.stringStart +
    pyp.dictOf(_value, _section).ignore(pyp.pythonStyleComment) +
    pyp.stringEnd)


class ConfigSection(basics.ConfigSection):

    """Expose a section_contents from pyparsing as a ConfigSection.

    mke2fsformat also uses this.
    """

    def __init__(self, section):
        basics.ConfigSection.__init__(self)
        self.section = section

    def __contains__(self, name):
        return name in self.section

    def keys(self):
        return self.section.keys()

    def render_value(self, central, name, arg_type):
        value = self.section[name]
        if arg_type == 'callable':
            if len(value) != 1:
                raise errors.ConfigurationError('only one argument required')
            value = value[0]
            if not isinstance(value, basestring):
                raise errors.ConfigurationError(
                    'need a callable, not a section')
            try:
                value = modules.load_attribute(value)
            except modules.FailedImport:
                raise errors.ConfigurationError('cannot import %r' % (value,))
            if not callable(value):
                raise errors.ConfigurationError('%r is not callable' % value)
            return value
        elif arg_type.startswith('ref:'):
            if len(value) != 1:
                raise errors.ConfigurationError('only one argument required')
            value = value[0]
            if isinstance(value, basestring):
                # it's a section ref
                return basics.LazyNamedSectionRef(central, arg_type, value)
            else:
                # it's an anonymous inline section
                return basics.LazyUnnamedSectionRef(central, arg_type,
                                                    ConfigSection(value))
        elif arg_type.startswith('refs:'):
            result = []
            for ref in value:
                if isinstance(ref, basestring):
                    # it's a section ref
                    result.append(basics.LazyNamedSectionRef(
                            central, arg_type, ref))
                else:
                    # it's an anonymous inline section
                    result.append(basics.LazyUnnamedSectionRef(
                            central, arg_type, ConfigSection(ref)))
            return None, result, None
        elif arg_type == 'list':
            if not isinstance(value, basestring):
                # sequence
                value = ' '.join(value)
            return None, basics.str_to_list(value), None
        elif arg_type == 'repr':
            if len(value) == 1:
                value = value[0]
                if isinstance(value, basestring):
                    return 'str', value
                return 'ref', ConfigSection(value)
            if all(isinstance(v, basestring) for v in value):
                return 'list', list(value)
            result = []
            for v in value:
                if not isinstance(v, basestring):
                    v = ConfigSection(v)
                result.append(v)
            return 'refs', result
        else:
            if len(value) != 1:
                raise errors.ConfigurationError('only one argument required')
            if not isinstance(value[0], basestring):
                raise errors.ConfigurationError(
                    '%r should be a string' % value)
            if arg_type == 'str':
                return [None, basics.str_to_str(value[0]), None]
            elif arg_type == 'bool':
                return basics.str_to_bool(value[0])
            else:
                raise errors.ConfigurationError(
                    'unsupported type %r' % (arg_type,))


def config_from_file(file_obj):
    try:
        config = parser.parseFile(file_obj)
    except pyp.ParseException, e:
        name = getattr(file_obj, 'name', file_obj)
        raise errors.ConfigurationError('%s: %s' % (name, e))
    def build_section(name):
        return ConfigSection(config[name])
    return mappings.LazyValDict(config.keys, build_section)
