"""base package class; instances should derive from this.

Right now, doesn't provide much, need to change that down the line
"""

__all__ = ("base", "wrapper", "dynamic_getattr_dict", "DynamicGetattrSetter")

import itertools

from snakeoil import klass, sequences

from .. import exceptions as base_errors
from ..operations import format
from . import errors


class base(klass.SlotsPicklingMixin, metaclass=klass.immutable_instance):

    built = False
    configurable = False
    _operations = format.operations

    __slots__ = ("__weakref__",)
    _get_attr = {}

    @property
    def versioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")

    @property
    def unversioned_atom(self):
        raise NotImplementedError(self, "unversioned_atom")

    def operations(self, domain, **kwds):
        return self._operations(domain, self, **kwds)

    @property
    def is_supported(self):
        return True


class wrapper(base):

    __slots__ = ("_raw_pkg", "_domain")

    def operations(self, domain, **kwds):
        return self._raw_pkg._operations(domain, self, **kwds)

    def __init__(self, raw_pkg):
        object.__setattr__(self, "_raw_pkg", raw_pkg)

    def __eq__(self, other):
        if isinstance(other, wrapper):
            return self._raw_pkg == other._raw_pkg
        try:
            return self._raw_pkg == other
        except TypeError:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        if isinstance(other, wrapper):
            return self._raw_pkg < other._raw_pkg
        return self._raw_pkg < other

    def __le__(self, other):
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other):
        if isinstance(other, wrapper):
            return self._raw_pkg > other._raw_pkg
        return self._raw_pkg > other

    def __ge__(self, other):
        return self.__gt__(other) or self.__eq__(other)

    __getattr__ = klass.GetAttrProxy("_raw_pkg")
    __dir__ = klass.DirProxy("_raw_pkg")

    _get_attr = klass.alias_attr("_raw_pkg._get_attr")
    built = klass.alias_attr("_raw_pkg.built")
    versioned_atom = klass.alias_attr("_raw_pkg.versioned_atom")
    unversioned_atom = klass.alias_attr("_raw_pkg.unversioned_atom")
    is_supported = klass.alias_attr('_raw_pkg.is_supported')

    def __hash__(self):
        return hash(self._raw_pkg)


def dynamic_getattr_dict(self, attr):
    functor = self._get_attr.get(attr)
    if functor is None:
        raise AttributeError(self, attr)
    try:
        val = functor(self)
        object.__setattr__(self, attr, val)
        return val
    except errors.MetadataException as e:
        if e.attr == attr:
            raise
        raise errors.MetadataException(self, attr, e.error, e.verbose) from e
    except (errors.PackageError, UnicodeDecodeError) as e:
        raise errors.MetadataException(self, attr, str(e)) from e
    except PermissionError as e:
        raise base_errors.PermissionDenied(self.path, write=False) from e


class DynamicGetattrSetter(type):
    """Metaclass utilizing __getattr__ to JIT generate attributes and store them.

    Consider `snakeoil.klass.jit_attr` for comparison; that pseudo property
    will invoke a functor and store the result, but every subsequent access- still
    pays overhead of passing through the redirects.

    This metaclass lacks that overhead; via hooking __getattr__, this generates
    the requested attribute, stores it on the instance, and returns it.  All
    future access of that attribute go through the fast path cpy access ways.

    This optimization in the early days of pkgcore had drastic impact; in modern
    times python has improved.  There still is gain, but the implementation complexity
    may warrant phasing this out in favor of `snakeoil.klas.jit_attr` alternatives.
    """

    class register:
        """Decorator used to mark a function as an attribute loader."""

        __slots__ = ('functor',)

        def __init__(self, functor):
            self.functor = functor

    def __new__(cls, name, bases, class_dict):
        new_functions = {
            attr: class_dict.pop(attr).functor
            for attr, thing in list(class_dict.items())
            if isinstance(thing, cls.register)
        }

        existing = {}
        for base in bases:
            existing.update(getattr(base, '_get_attr', {}))

        slots = class_dict.get('__slots__', None)
        if slots is not None:
            # only add slots for new attr's; assume the layer above already slotted
            # if this layer is setting slots.
            class_dict['__slots__'] = tuple(
                sequences.iter_stable_unique(
                    itertools.chain(
                        slots,
                        set(new_functions).difference(existing)
                    )
                )
            )

        d = existing if class_dict.pop('__DynamicGetattrSetter_auto_inherit__', True) else {}
        d.update(new_functions)
        d.update(class_dict.pop('_get_attr', {}))
        class_dict['_get_attr'] = d
        class_dict.setdefault('__getattr__', dynamic_getattr_dict)

        return type.__new__(cls, name, bases, class_dict)
