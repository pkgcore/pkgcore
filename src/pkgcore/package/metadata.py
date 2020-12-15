"""package with its metadata accessible (think 'no longer abstract')"""

__all__ = ("DeriveMetadataKls", "factory", "package")

from snakeoil import klass, weakrefs

from ..ebuild import cpv
from ..ebuild.atom import atom
from . import base


def DeriveMetadataKls(original_kls):
    if getattr(original_kls, "_derived_metadata_kls", False):
        return original_kls

    class package(original_kls, metaclass=base.DynamicGetattrSetter):
        _derived_metadata_kls = True
        built = False
        __slots__ = ("_parent", "data", "_domain")
        try:
            __doc__ = "package class with metadata bound to it for attribute " \
                "generation\n\n" + \
                     "\n".join(x.lstrip()
                          for x in original_kls.__doc__.split("\n")
                          if ":ivar" in x or ":cvar" in x)
            __doc__ += "\n:ivar repo: parent repository"
        except AttributeError:
            # wee, must be in -OO mode.
            __doc__ = None

        immutable = True
        package_is_real = True

        def __init__(self, parent_repository, *args, **kwds):
            f"""wrapper for {original_kls}.__init__
            
            See {original_kls}.__init__ for allowed args/kwds, they're passed
            directly to it.

            :param parent_repository: parent repository this package belongs to
            :type parent_repository: :obj:`pkgcore.repository.prototype.tree`
                instance
            """
            super().__init__(*args, **kwds)
            object.__setattr__(self, '_parent',  parent_repository)

        @base.DynamicGetattrSetter.register
        def data(self):
            """internal hook func to get the packages metadata"""
            return self._fetch_metadata()

        repo = klass.alias_attr("_parent._parent_repo")

        def release_cached_data(self, all=False):
            for x in self._get_attr:
                try:
                    object.__delattr__(self, x)
                except AttributeError:
                    pass

            if all:
                try:
                    object.__delattr__(self, 'data')
                except AttributeError:
                    pass

        @property
        def slotted_atom(self):
            return atom(f'{self.key}:{self.slot}')

        def _fetch_metadata(self):
            """Pull the metadata for this package.

            Must be overridden in derivatives.
            """
            raise NotImplementedError

        def add_format_triggers(self, op_inst, format_op_inst, engine_inst):
            pass

    return package

package = DeriveMetadataKls(cpv.VersionedCPV)

class factory:
    """package generator

    does weakref caching per repository

    :cvar child_class: callable to generate packages
    """

    child_class = package

    def __init__(self, parent_repo):
        self._parent_repo = parent_repo
        self._cached_instances = weakrefs.WeakValCache()

    def new_package(self, *args):
        """generate a new package instance"""
        inst = self._cached_instances.get(args)
        if inst is None:
            inst = self._cached_instances[args] = self.child_class(self, *args)
        return inst

    def __call__(self, *args, **kwds):
        return self.new_package(*args, **kwds)

    def clear(self):
        """wipe the weakref cache of packages instances"""
        self._cached_instances.clear()

    def _get_metadata(self, *args):
        """Pulls metadata from the repo/cache/wherever.

        Must be overridden in derivatives.
        """
        raise NotImplementedError

    def _update_metadata(self, *args):
        """Updates metadata in the repo/cache/wherever.

        Must be overridden in derivatives.
        """
        raise NotImplementedError

    def __getstate__(self):
        d = self.__dict__.copy()
        del d['_cached_instances']
        return d

    def __setstate__(self, state):
        self.__dict__ = state.copy()
        self.__dict__['_cached_instances'] = weakrefs.WeakValCache()
