__all__ = ("get_raw_pkg", "groupby_pkg")

import itertools
from operator import attrgetter


def get_raw_pkg(pkg):
    p = pkg
    while hasattr(p, "_raw_pkg"):
        p = p._raw_pkg
    return p


def groupby_pkg(iterable):
    for key, pkgs in itertools.groupby(iterable, attrgetter('key')):
        yield pkgs
