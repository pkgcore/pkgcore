"""
base restriction class
"""

import abc
import functools
import typing

from snakeoil import klass
from snakeoil.currying import pretty_docs
from snakeoil.klass import immutable, memoize

type T_restriction = str
value_type = "values"
package_type = "package"
valid_types = (value_type, package_type)


class base(klass.SlotsPicklingMixin, immutable.Simple, memoize.WeaklyCachedABC):
    """base restriction matching object.

    all derivatives *should* be __slots__ based (lot of instances may
    wind up in memory).
    """

    # __weakref__ here is implicit via the metaclass
    __slots__ = ()
    type: T_restriction
    package_matching: typing.ClassVar[bool] = False

    @abc.abstractmethod
    def match(self, *arg, **kwargs) -> bool:
        raise NotImplementedError

    def force_False(self, *arg, **kwargs) -> bool:
        return not self.match(*arg, **kwargs)

    def force_True(self, *arg, **kwargs) -> bool:
        return self.match(*arg, **kwargs)

    # TODO: deprecate this exact call.  It has no meaning, len exists
    # due to early restriction subsystem development- introspection tools
    # should instead exist, or a saner protocol.
    def __len__(self) -> int:
        return 1


class AlwaysBool(base):
    """restriction that always yields a specific boolean"""

    __slots__ = ("negate", "type")
    type: T_restriction
    negate: bool

    def __init__(self, node_type: T_restriction, negate: bool = False):
        """
        :param node_type: the restriction type the instance should be,
            typically :obj:`pkgcore.restrictions.restriction.package_type` or
            :obj:`pkgcore.restrictions.restriction.value_type`
        :param negate: boolean to return for the match
        """
        self.negate = negate
        self.type = node_type

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
        return f"<{self.__class__.__name__} always {self.negate!r} @{id(self):#8x}>"

    def __getstate__(self):
        return self.negate, self.type

    def __setstate__(self, state):
        self.negate, self.type = state


# TODO: fix this so it's cachable.  It *is* cachable.
class Negate(base, caching=False):
    """wrap and negate a restriction instance"""

    __slots__ = ("_restrict", "type")
    type: T_restriction

    def __init__(self, restrict: base):
        """
        :param restrict: :obj:`pkgcore.restrictions.restriction.base` instance
            to negate
        """
        self.type = restrict.type
        self._restrict = restrict

    def match(self, *a, **kw):
        return not self._restrict.match(*a, **kw)

    def __str__(self):
        return f"not ({self._restrict})"


class FakeType(base, caching=False):
    """wrapper to wrap and fake a node_type"""

    __slots__ = ("_restrict", "type")

    def __init__(self, restrict: base, new_type: T_restriction):
        """
        :param restrict: :obj:`pkgcore.restrictions.restriction.base` instance
            to wrap
        :param new_type: new node_type
        """
        self.type = new_type
        self._restrict = restrict

    def match(self, *a, **kw):
        return self._restrict.match(*a, **kw)

    def __str__(self):
        return f"Faked type({self.type}): {self._restrict}"


class AnyMatch(base):
    """Apply a nested restriction to every item in a sequence."""

    __slots__ = ("negate", "restriction", "type")

    def __init__(self, childrestriction: base, node_type: T_restriction, negate=False):
        """Initialize.

        :type childrestriction: restriction
        :param childrestriction: child restriction applied to every value.
        :type node_type: string
        :param node_type: type of this restriction.
        """
        self.negate = negate
        self.restriction = childrestriction
        self.type = node_type

    def match(self, val):
        for x in val:
            if self.restriction.match(x):
                return not self.negate
        return self.negate

    def __str__(self):
        return f"any: {self.restriction} match"

    def __repr__(self):
        return f"<{self.__class__.__name__} restriction={self.restriction!r} @{id(self):#8x}>"


def curry_node_type(cls, node_type: T_restriction, extradoc=None):
    """Helper function for creating restrictions of a certain type.

    This uses :obj:`functools.partial` to pass a node_type to the wrapped class,
    and extends the docstring.

    :param cls: callable (usually a class) that is wrapped.
    :param node_type: value passed as node_type.
    :param extradoc: addition to the docstring. Defaults to
        "Automatically set to %s type." % node_type

    :return: a wrapped callable.
    """
    if extradoc is None:
        extradoc = f"Automatically set to {node_type} type."
    doc = cls.__doc__
    result = functools.partial(cls, node_type=node_type)
    if doc is None:
        doc = ""
    else:
        # do this so indentation on pydoc __doc__ is sane
        doc = "\n".join(line.lstrip() for line in doc.split("\n")) + "\n"
        doc += extradoc
    return pretty_docs(result, doc)
