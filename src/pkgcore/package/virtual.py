"""
virtual package
"""

__all__ = ("package", "factory")

from ..restrictions.packages import OrRestriction
from . import metadata


class package(metadata.package):

    """
    Virtual package.

    Mainly useful since it's generating so little attrs on the fly.
    """

    package_is_real = False
    built = True

    __slots__ = ("__dict__",)

    def __init__(self, repo, provider, *a, **kwds):
        super().__init__(repo, *a, **kwds)
        object.__setattr__(self, 'provider', provider)
        object.__setattr__(self, 'data', {})

    def __getattr__(self, key):
        val = None
        if key == "rdepend":
            val = self.provider
        elif key in ("bdepend", "depend", "pdepend"):
            val = OrRestriction()
        elif key == "slot":
            val = f"{self.provider.category}-{self.version}"
        else:
            return super().__getattr__(key)
        self.__dict__[key] = val
        return val

    def _fetch_metadata(self):
        data = self._parent._parent_repo._fetch_metadata(self)
        return data


class factory(metadata.factory):
    child_class = package
