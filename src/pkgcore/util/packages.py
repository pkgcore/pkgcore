__all__ = ("get_raw_pkg", "groupby_pkg")

import itertools
import operator


def get_raw_pkg(pkg):
    p = pkg
    while hasattr(p, "_raw_pkg"):
        p = p._raw_pkg
    return p

groupby_key_getter = operator.attrgetter("key")
def groupby_pkg(iterable):
    for key, pkgs in itertools.groupby(iterable, groupby_key_getter):
        yield pkgs
