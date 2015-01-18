# Copyright: 2009 Brian Harring <ferringb@gmail.com>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
ini based configuration format
"""

__all__ = ("config_from_file",)

from snakeoil import mappings
from snakeoil.compatibility import configparser

from pkgcore.config import basics, errors


class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, val):
        return val


def config_from_file(file_obj):
    """
    generate a config dict

    :param file_obj: file protocol instance
    :return: :obj:`snakeoil.mappings.LazyValDict` instance
    """
    cparser = CaseSensitiveConfigParser()
    try:
        cparser.read_file(file_obj)
    except configparser.ParsingError as pe:
        raise errors.ParsingError("while parsing %s" % (file_obj,), pe)
    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)
