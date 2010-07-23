# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
wrap a repository, binding configuration to pkgs returned from the repository
"""

from pkgcore.repository import prototype
from pkgcore.package.conditionals import make_wrapper
from pkgcore.operations.repo import operations_proxy
from snakeoil.currying import partial
from snakeoil.klass import GetAttrProxy


class tree(prototype.tree):
    configured = True

    operations_kls = operations_proxy

    def __init__(self, raw_repo, wrapped_attrs, pkg_kls_injections=()):

        """
        @param raw_repo: repo to wrap
        @type raw_repo: L{pkgcore.repository.prototype.tree}
        @param wrapped_attrs: sequence of attrs to wrap for each pkg
        """

        # yes, we're intentionally not using tree's init.
        # not perfect I know.
        self.raw_repo = raw_repo
        self.wrapped_attrs = wrapped_attrs
        self.attr_filters = frozenset(wrapped_attrs.keys() +
                                      [self.configurable])

        self._klass = self._mk_kls(pkg_kls_injections)

    def _mk_kls(self, pkg_kls_injections):
        return make_wrapper(self.configurable, self.wrapped_attrs,
            kls_injections=pkg_kls_injections)

    def _get_pkg_kwds(self, pkg):
        raise NotImplementedError()

    def package_class(self, pkg, *a):
        return self._klass(pkg, **self._get_pkg_kwds(pkg))

    __getattr__ = GetAttrProxy("raw_repo")

    def itermatch(self, restrict, **kwds):
        kwds.setdefault("force", True)
        o = kwds.get("pkg_klass_override")
        if o is not None:
            kwds["pkg_klass_override"] = partial(self.package_class, o)
        else:
            kwds["pkg_klass_override"] = self.package_class
        return self.raw_repo.itermatch(restrict, **kwds)

    itermatch.__doc__ = prototype.tree.itermatch.__doc__.replace(
        "@param", "@keyword").replace("@keyword restrict:", "@param restrict:")

    def __getitem__(self, key):
        return self.package_class(self.raw_repo[key])

    def __repr__(self):
        return '<%s.%s raw_repo=%r wrapped=%r @%#8x>' % (
            self.__class__.__module__, self.__class__.__name__,
            getattr(self, 'raw_repo', 'unset'),
            getattr(self, 'wrapped_attrs', {}).keys(),
            id(self))
