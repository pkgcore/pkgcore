# Copyright: 2009 Brian Harring <ferringb@gmail.com>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
ini based configuration format
"""

__all__ = ("config_from_file",)

import ConfigParser
import sys

from pkgcore.config import basics, errors
from snakeoil import mappings

class CaseSensitiveConfigParser(ConfigParser.ConfigParser):
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
        if sys.hexversion < 0x03020000:
            cparser.readfp(file_obj)
        else:
            cparser.read_file(file_obj)
    except ConfigParser.ParsingError, pe:
        raise errors.ParsingError("while parsing %s" % (file_obj,), pe)
    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)
