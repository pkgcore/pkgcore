"""
conditional attributes on a package.

Changing them triggering regen of other attributes on the package instance.
"""

__all__ = ("make_wrapper",)

from copy import copy
from functools import partial
from operator import attrgetter

from snakeoil.containers import LimitedChangeSet, Unchangable

from .base import wrapper


def _getattr_wrapped(attr, self):
    o = self._cached_wrapped.get(attr)
    if o is None or o[0] != self._reuse_pt:
        o = self._wrapped_attr[attr](
            getattr(self._raw_pkg, attr),
            self._configurable,
            pkg=self)
        o = self._cached_wrapped[attr] = (self._reuse_pt, o)
    return o[1]


def make_wrapper(wrapped_repo, configurable_attribute_name, attributes_to_wrap=(),
                 kls_injections={}):
    """
    :param configurable_attribute_name: attribute name to add,
        and that is used for evaluating attributes_to_wrap
    :param attributes_to_wrap: mapping of attr_name:callable
        for revaluating the pkg_instance, using the result
        instead of the wrapped pkgs attr.
    """

    if configurable_attribute_name.find(".") != -1:
        raise ValueError("can only wrap first level attributes, "
                         "'obj.dar' fex, not '%s'" %
                         (configurable_attribute_name))

    class PackageWrapper(wrapper):
        """Add a new attribute, and evaluate attributes of a wrapped pkg."""

        __slots__ = (
            "_unchangable", "_configurable", "_reuse_pt",
            "_cached_wrapped", "_disabled", "_domain", "repo",
        )

        _wrapped_attr = attributes_to_wrap
        _configurable_name = configurable_attribute_name
        configurable = True

        def operations(self, domain, **kwds):
            return self._operations(domain, self, **kwds)

        locals()[configurable_attribute_name] = property(attrgetter("_configurable"))

        locals().update(
            (x, property(partial(_getattr_wrapped, x)))
            for x in attributes_to_wrap)

        def __init__(self, pkg_instance, initial_settings=None,
                     disabled_settings=None, unchangable_settings=None):
            """
            :type pkg_instance: :obj:`pkgcore.package.metadata.package`
            :param pkg_instance: instance to wrap.
            :type initial_settings: sequence
            :param initial_settings: initial configuration of the
                configurable_attribute
            :type unchangable_settings: sequence
            :param unchangable_settings: settings that configurable_attribute
                cannot be set to
            """

            if initial_settings is None:
                initial_settings = []
            if disabled_settings is None:
                disabled_settings = []
            if unchangable_settings is None:
                unchangable_settings = []

            sf = object.__setattr__
            sf(self, '_unchangable', unchangable_settings)
            sf(self, '_configurable', LimitedChangeSet(
                initial_settings, unchangable_settings))
            sf(self, '_disabled', disabled_settings)
            sf(self, '_reuse_pt', 0)
            sf(self, 'repo', wrapped_repo)
            sf(self, '_cached_wrapped', {})
            sf(self, '_domain', None)
            super().__init__(pkg_instance)

        def __copy__(self):
            return self.__class__(
                self._raw_pkg, self._configurable_name,
                initial_settings=set(self._configurable),
                disabled_settings=self._disabled,
                unchangable_settings=self._unchangable,
                attributes_to_wrap=self._wrapped_attr)

        def rollback(self, point=0):
            """rollback changes to the configurable attribute to an earlier point

            :param point: must be an int
            """
            self._configurable.rollback(point)
            # yes, nuking objs isn't necessarily required.  easier this way though.
            # XXX: optimization point
            object.__setattr__(self, '_reuse_pt', self._reuse_pt + 1)

        def commit(self):
            """Commit current changes.

            This means that those changes can be reverted from this point out.
            """
            self._configurable.commit()
            object.__setattr__(self, '_reuse_pt',  0)

        def changes_count(self):
            """current commit point for the configurable"""
            return self._configurable.changes_count()

        def request_enable(self, attr, *vals):
            """internal function

            since configurable somewhat steps outside of normal
            restriction protocols, request_enable requests that this
            package instance change its configuration to make the
            restriction return True; if not possible, reverts any changes
            it attempted

            :param attr: attr to try and change
            :param vals: :obj:`pkgcore.restrictions.values.base` instances that
                we're attempting to make match True
            """
            if attr not in self._wrapped_attr:
                if attr == self._configurable_name:
                    entry_point = self.changes_count()
                    try:
                        list(map(self._configurable.add, vals))
                        object.__setattr__(self, '_reuse_pt', self._reuse_pt + 1)
                        return True
                    except Unchangable:
                        self.rollback(entry_point)
                else:
                    a = getattr(self._raw_pkg, attr)
                    for x in vals:
                        if x not in a:
                            break
                    else:
                        return True
                return False
            entry_point = self.changes_count()
            a = getattr(self._raw_pkg, attr)
            try:
                for x in vals:
                    for reqs in a.node_conds.get(x, ()):
                        if reqs.force_True(self, attr, vals):
                            break
                    else:
                        self.rollback(entry_point)
                        return False
            except Unchangable:
                self.rollback(entry_point)
                return False
            object.__setattr__(self, '_reuse_pt', self._reuse_pt + 1)
            return True

        def request_disable(self, attr, *vals):
            """internal function

            since configurable somewhat steps outside of normal
            restriction protocols, request_disable requests that this
            package instance change its configuration to make the
            restriction return False; if not possible, reverts any changes
            it attempted

            :param attr: attr to try and change
            :param vals: :obj:`pkgcore.restrictions.values.base` instances that
                we're attempting to make match False
            """
            if attr not in self._wrapped_attr:
                if attr == self._configurable_name:
                    entry_point = self.changes_count()
                    try:
                        list(map(self._configurable.remove, vals))
                        return True
                    except Unchangable:
                        self.rollback(entry_point)
                else:
                    a = getattr(self._raw_pkg, attr)
                    for x in vals:
                        if x in a:
                            break
                    else:
                        return True
                return False
            entry_point = self.changes_count()
            a = getattr(self._raw_pkg, attr)
            try:
                for x in vals:
                    for reqs in a.node_conds.get(x, ()):
                        if reqs.force_False(self, attr, vals):
                            break
                    else:
                        self.rollback(entry_point)
                        return False
            except Unchangable:
                self.rollback(entry_point)
                return False
            object.__setattr__(self, '_reuse_pt', self._reuse_pt + 1)
            return True

        def __str__(self):
            return "config wrapped(%s): %s" % (self._configurable_name,
                                               self._raw_pkg)

        def __repr__(self):
            return "<%s pkg=%r wrapped=%r @%#8x>" % (
                self.__class__.__name__, self._raw_pkg, self._configurable_name,
                id(self))

        def freeze(self):
            o = copy(self)
            o.lock()
            return o

        def lock(self):
            """
            commit any outstanding changes and lock the configuration.
            """
            self.commit()
            object.__setattr__(self, '_configurable', list(self._configurable))

        if 'operations_callback' in kls_injections:
            _operations = kls_injections.pop("operations_callback")
        locals().update(kls_injections)

    return PackageWrapper
