# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""
ini based configuration format
"""

from ConfigParser import ConfigParser

from pkgcore.util import mappings

from pkgcore.config import basics, errors


class CaseSensitiveConfigParser(ConfigParser):
    def optionxform(self, val):
        return val


def configFromIni(file_obj):
    """
    generate a config dict
    
    @param file_obj: file protocol instance
    @return: L{pkgcore.util.mappings.LazyValDict} instance
    """
    cparser = CaseSensitiveConfigParser()
    cparser.readfp(file_obj)
    def get_section(section):
        return basics.ConfigSectionFromStringDict(
            section, dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)


def configTypesFromIni(file_object):
    """parse config types from ini file object"""
    types = {}
    config = CaseSensitiveConfigParser()
    config.readfp(file_object)
    default_keys = config.defaults().keys()
    for type_name in config.sections():
        # parse everything in the type definition config that
        # should be a list
        type_config = dict(config.items(type_name))
        allow_unknowns = bool(type_config.pop("allow_unknowns", False))
        incrementals = tuple(basics.list_parser(
                type_config.pop('incrementals', '')))
        required = tuple(basics.list_parser(
                type_config.pop('required', '')))
        positional = tuple(basics.list_parser(
                type_config.pop('positional', '')))
        # build a dict mapping config args to their type name
        arg_types = {}
        for arg_type_name in basics.type_names:
            for arg_name in basics.list_parser(
                type_config.pop(arg_type_name, '')):
                if arg_name in arg_types:
                    raise errors.TypeDefinitionError(
                        '%s: more than one type for %r' %
                        (type_name, arg_name))
                arg_types[arg_name] = arg_type_name

        defaults = {}
        for default in basics.list_parser(type_config.pop('defaults', '')):
            try:
                defaults[default] = type_config.pop(default)
            except KeyError:
                raise errors.TypeDefinitionError(
                    '%s: no default value for %r' % (type_name, default))
        defaults = basics.ConfigSectionFromStringDict(
            'defaults for %r' % type_name, defaults)
        # check if everything in the definition was used. Ignore the
        # DEFAULT bits.
        for key in default_keys:
            type_config.pop(key, None)
        if type_config:
            raise errors.TypeDefinitionError(
                '%s: unused type configuration data %r' %
                (type_name, type_config))

        types[type_name] = basics.ConfigType(
            type_name, arg_types,
            incrementals=incrementals, positional=positional,
            required=required, defaults=defaults, allow_unknowns=allow_unknowns)
    return types
