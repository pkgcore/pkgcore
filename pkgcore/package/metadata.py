# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


"""
package with it's metadata accessible (think 'no longer abstract')
"""

from pkgcore.util.weakrefs import WeakValCache

from pkgcore.util.demandload import demandload
demandload(globals(), "warnings")

from pkgcore.ebuild.cpv import CPV
from pkgcore.package.atom import atom

def DeriveMetadataKls(original_kls):
    if getattr(original_kls, "_derived_metadata_kls", False):
        return original_kls
    
    class package(original_kls):
        _derived_metadata_kls = True
        built = False
        try:
            __doc__ = "package class with metadata bound to it for attribute " \
                "generation\n\n" + \
                     "\n".join(x.lstrip()
                          for x in original_kls.__doc__.split("\n")
                          if "@ivar" in x or "@cvar" in x)
            __doc__ += "\n@ivar repo: parent repository"
        except AttributeError:
            # wee, must be in -OO mode.
            __doc__ = None

        immutable = True
        package_is_real = True

        _get_attr = dict(original_kls._get_attr)

        def __init__(self, parent_repository, *a, **kwds):
            """
            wrapper for %s.__init__; see %s.__init__ for allowed args/kwds, 
                they're passed directly to it

            @param parent_repository: parent repository this package belongs to
            @type parent_repository: L{pkgcore.repository.prototype.tree} 
                instance
            """
            original_kls.__init__(self, *a, **kwds)
            self.__dict__["_parent"] = parent_repository

        def _get_data(self):
            """
            internal hook func to get the packages metadata, consumer
            of L{_get_attr}
            """
            if "data" in self.__dict__:
                warnings.warn(
                    "odd, got a request for data yet it's in the dict")
                return self.__dict__["data"]

            return self._fetch_metadata()
        _get_attr["data"] = _get_data

        @property
        def repo(self):
            return self._parent._parent_repo

        @property
        def slotted_atom(self):
            return atom("%s:%s" % (self.key, self.slot))

        def _fetch_metadata(self):
            """
            pull the metadata for this package.
            must be overrode in derivative
            """
            raise NotImplementedError

        def add_format_triggers(self, op_inst, format_op_inst, engine_inst):
            pass

    return package

package = DeriveMetadataKls(CPV)

class factory(object):

    """
    package generator

    does weakref caching per repository

    @cvar child_class: callable to generate packages
    """

    child_class = package

    def __init__(self, parent_repo):
        self._parent_repo = parent_repo
        self._cached_instances = WeakValCache()

    def new_package(self, cpv):
        """
        generate a new package instance

        @param cpv: cpvstring to parse for the new package
            (gentoo specific, abstract this out)
        @type cpv: string
        """

        inst = self._cached_instances.get(cpv)
        if inst is None:
            inst = self._cached_instances[cpv] = self.child_class(self, cpv)
        return inst

    def __call__(self, *args, **kwds):
        return self.new_package(*args, **kwds)

    def clear(self):
        """
        wipe the weakref cache of packages instances
        """
        self._cached_instances.clear()

    def _get_metadata(self, *args):
        """Pulls metadata from the repo/cache/wherever.

        Must be overriden in derivatives.
        """
        raise NotImplementedError

    def _update_metadata(self, *args):
        """Updates metadata in the repo/cache/wherever.

        Must be overriden in derivatives."""
        raise NotImplementedError
