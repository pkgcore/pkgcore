"""
ini based configuration format
"""

__all__ = ("config_from_file",)

import configparser
import typing

from snakeoil import mappings

from . import basics, errors


class CaseSensitiveConfigParser(configparser.ConfigParser):
    """Parse to enforce case sensitivity for configparser"""

    def optionxform(self, optionstr: str) -> str:
        """preserve case sensitivity"""
        return optionstr


def config_from_file(file_obj: typing.Iterable[str]) -> mappings.LazyValDict:
    """
    generate a config dict

    :param file_obj: file protocol instance
    :return: :obj:`snakeoil.mappings.LazyValDict` instance
    """
    cparser = CaseSensitiveConfigParser()
    try:
        cparser.read_file(file_obj)
    except configparser.ParsingError as e:
        raise errors.ParsingError(f"while parsing {file_obj}", e) from e

    def get_section(section):
        return basics.ConfigSectionFromStringDict(dict(cparser.items(section)))

    return mappings.LazyValDict(cparser.sections, get_section)
