# Copyright: 2009 Brian Harring <ferringb@gmail.com>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""
ini based configuration format
"""

import ConfigParser

from pkgcore.config import basics, errors
from snakeoil import mappings

class CaseSensitiveConfigParser(ConfigParser.ConfigParser):
    def optionxform(self, val):
        return val


def config_from_file(file_obj):
    """
    generate a config dict

    @param file_obj: file protocol instance
    @return: L{snakeoil.mappings.LazyValDict} instance
    """
    cparser = CaseSensitiveConfigParser()
    try:
        cparser.readfp(file_obj)
    except ConfigParser.ParsingError, pe:
        raise errors.ParsingError("while parsing %s" % (file_obj,), pe)
    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)
