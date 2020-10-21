"""
base restriction class
"""

from functools import partial

from snakeoil import caching, klass
from snakeoil.currying import pretty_docs


class base(klass.SlotsPicklingMixin, metaclass=caching.WeakInstMeta):
    """base restriction matching object.

    all derivatives *should* be __slots__ based (lot of instances may
    wind up in memory).
    """
    __inst_caching__ = True

    # __weakref__ here is implicit via the metaclass
    __slots__ = ()
    package_matching = False

    klass.inject_immutable_instance(locals())

    def match(self, *arg, **kwargs):
        raise NotImplementedError

    def force_False(self, *arg, **kwargs):
        return not self.match(*arg, **kwargs)

    def force_True(self, *arg, **kwargs):
        return self.match(*arg, **kwargs)

    def __len__(self):
        return 1


class AlwaysBool(base):
    """restriction that always yields a specific boolean"""

    __slots__ = ("type", "negate")

    __inst_caching__ = True

    def __init__(self, node_type=None, negate=False):
        """
        :param node_type: the restriction type the instance should be,
            typically :obj:`pkgcore.restrictions.restriction.package_type` or
            :obj:`pkgcore.restrictions.restriction.value_type`
        :param negate: boolean to return for the match
        """
        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "type", node_type)

    def match(self, *a, **kw):
        return self.negate

    def force_True(self, *a, **kw):
        return self.negate

    def force_False(self, *a, **kw):
        return not self.negate

    def __iter__(self):
        return iter(())

    def __str__(self):
        return f"always '{self.negate}'"

    def __repr__(self):
        return '<%s always %r @%#8x>' % (
            self.__class__.__name__, self.negate, id(self))

    def __getstate__(self):
        return self.negate, self.type

    def __setstate__(self, state):
        negate, node_type = state
        object.__setattr__(self, "negate", negate)
        object.__setattr__(self, "type", node_type)


class Negate(base):
    """wrap and negate a restriction instance"""

    __slots__ = ("type", "_restrict")
    __inst_caching__ = False

    def __init__(self, restrict):
        """
        :param restrict: :obj:`pkgcore.restrictions.restriction.base` instance
            to negate
        """
        sf = object.__setattr__
        sf(self, "type", restrict.type)
        sf(self, "_restrict", restrict)

    def match(self, *a, **kw):
        return not self._restrict.match(*a, **kw)

    def __str__(self):
        return "not (%s)" % self._restrict


class FakeType(base):
    """wrapper to wrap and fake a node_type"""

    __slots__ = ("type", "_restrict")
    __inst_caching__ = False

    def __init__(self, restrict, new_type):
        """
        :param restrict: :obj:`pkgcore.restrictions.restriction.base` instance
            to wrap
        :param new_type: new node_type
        """
        sf = object.__setattr__
        sf(self, "type", new_type)
        sf(self, "_restrict", restrict)

    def match(self, *a, **kw):
        return self._restrict.match(*a, **kw)

    def __str__(self):
        return "Faked type(%s): %s" % (self.type, self._restrict)


class AnyMatch(base):
    """Apply a nested restriction to every item in a sequence."""

    __slots__ = ('restriction', 'type', 'negate')

    def __init__(self, childrestriction, node_type, negate=False):
        """Initialize.

        :type childrestriction: restriction
        :param childrestriction: child restriction applied to every value.
        :type node_type: string
        :param node_type: type of this restriction.
        """
        sf = object.__setattr__
        sf(self, "negate", negate)
        sf(self, "restriction", childrestriction)
        sf(self, "type", node_type)

    def match(self, val):
        for x in val:
            if self.restriction.match(x):
                return not self.negate
        return self.negate

    def __str__(self):
        return "any: %s match" % (self.restriction,)

    def __repr__(self):
        return '<%s restriction=%r @%#8x>' % (
            self.__class__.__name__, self.restriction, id(self))


def curry_node_type(cls, node_type, extradoc=None):
    """Helper function for creating restrictions of a certain type.

    This uses :obj:`partial` to pass a node_type to the wrapped class,
    and extends the docstring.

    :param cls: callable (usually a class) that is wrapped.
    :param node_type: value passed as node_type.
    :param extradoc: addition to the docstring. Defaults to
        "Automatically set to %s type." % node_type

    :return: a wrapped callable.
    """
    if extradoc is None:
        extradoc = "Automatically set to %s type." % (node_type,)
    doc = cls.__doc__
    result = partial(cls, node_type=node_type)
    if doc is None:
        doc = ''
    else:
        # do this so indentation on pydoc __doc__ is sane
        doc = "\n".join(line.lstrip() for line in doc.split("\n")) + "\n"
        doc += extradoc
    return pretty_docs(result, doc)


value_type = "values"
package_type = "package"
valid_types = (value_type, package_type)
