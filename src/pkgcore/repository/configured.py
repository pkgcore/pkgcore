"""
wrap a repository, binding configuration to pkgs returned from the repository
"""

__all__ = ("tree",)

from functools import partial

from snakeoil.klass import DirProxy, GetAttrProxy

from ..operations.repo import operations_proxy
from ..package.conditionals import make_wrapper
from . import prototype


class tree(prototype.tree):

    configured = True
    operations_kls = operations_proxy

    def __init__(self, raw_repo, wrapped_attrs, pkg_kls_injections=()):
        """
        :param raw_repo: repo to wrap
        :type raw_repo: :obj:`pkgcore.repository.prototype.tree`
        :param wrapped_attrs: sequence of attrs to wrap for each pkg
        """
        # yes, we're intentionally not using tree's init.
        # not perfect I know.
        self.raw_repo = raw_repo
        self.wrapped_attrs = wrapped_attrs
        self._pkg_klass = self._mk_kls(pkg_kls_injections)

    def _mk_kls(self, pkg_kls_injections):
        return make_wrapper(
            self, self.configurable, self.wrapped_attrs,
            kls_injections=pkg_kls_injections)

    def _get_pkg_kwds(self, pkg):
        raise NotImplementedError

    def package_class(self, pkg):
        return self._pkg_klass(pkg, **self._get_pkg_kwds(pkg))

    @property
    def pkg_masks(self):
        # required to override empty pkg_masks inherited from prototype.tree
        return self.raw_repo.pkg_masks

    __getattr__ = GetAttrProxy("raw_repo")
    __dir__ = DirProxy("raw_repo")

    def itermatch(self, restrict, **kwds):
        kwds.setdefault("force", True)
        o = kwds.get("pkg_cls")
        if o is not None:
            kwds["pkg_cls"] = partial(self.package_class, o)
        else:
            kwds["pkg_cls"] = self.package_class
        return self.raw_repo.itermatch(restrict, **kwds)

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace(":keyword restrict:", ":param restrict:")

    def __getitem__(self, key):
        obj = self.package_class(self.raw_repo[key])
        if not obj.is_supported:
            raise KeyError(key)
        return obj

    def __repr__(self):
        return '<%s.%s raw_repo=%r wrapped=%r @%#8x>' % (
            self.__class__.__module__, self.__class__.__name__,
            getattr(self, 'raw_repo', 'unset'),
            list(getattr(self, 'wrapped_attrs', {}).keys()),
            id(self))
