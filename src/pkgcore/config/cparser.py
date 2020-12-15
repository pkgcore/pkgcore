"""
ini based configuration format
"""

__all__ = ("config_from_file",)

import configparser

from snakeoil import mappings

from . import basics, errors


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
    except configparser.ParsingError as e:
        raise errors.ParsingError(f'while parsing {file_obj}', e) from e
    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))
    return mappings.LazyValDict(cparser.sections, get_section)
