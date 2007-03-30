# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""
ini based configuration format
"""

from ConfigParser import ConfigParser

from pkgcore.config import basics
from snakeoil import mappings

class CaseSensitiveConfigParser(ConfigParser):
    def optionxform(self, val):
        return val


def config_from_file(file_obj):
    """
    generate a config dict

    @param file_obj: file protocol instance
    @return: L{snakeoil.mappings.LazyValDict} instance
    """
    cparser = CaseSensitiveConfigParser()
    cparser.readfp(file_obj)
    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)
