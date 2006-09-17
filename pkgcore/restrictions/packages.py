# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
restriction classes designed for package level matching
"""

import operator
from pkgcore.restrictions import restriction, boolean
from pkgcore.util.demandload import demandload
from pkgcore.util.compatibility import any
demandload(globals(), "logging")

# Backwards compatibility.
package_type = restriction.package_type


class PackageRestriction(restriction.base):

    """Package data restriction."""

    # Careful: some methods (__eq__, __hash__, intersect) try to work
    # for subclasses too. They will not behave as intended if a
    # subclass adds attributes. So if you do that, override the
    # methods.

    __slots__ = ("attr_split", "attr", "restriction", "ignore_missing")
    type = restriction.package_type
    subtype = restriction.value_type
    
    __inst_caching__ = True

    def __init__(self, attr, childrestriction, negate=False, ignore_missing=False):
        """
        @param attr: package attribute to match against
        @param childrestriction: a L{pkgcore.restrictions.values.base} instance
            to pass attr to for matching
        @param negate: should the results be negated?
        """
        if not childrestriction.type == self.subtype:
            raise TypeError("restriction must be of type %r" % (self.subtype,))
        super(PackageRestriction, self).__init__(negate=negate)
        sf = object.__setattr__
        sf(self, "attr_split", 
            tuple(operator.attrgetter(x) for x in attr.split(".")))
        sf(self, "attr", attr)
        sf(self, "restriction", childrestriction)
        sf(self, "ignore_missing", True)

    def __pull_attr(self, pkg):
        try:
            o = pkg
            for f in self.attr_split:
                o = f(o)
            return o
        except (KeyboardInterrupt, RuntimeError, SystemExit):
            raise
        except AttributeError,ae:
            if not self.ignore_missing:
                logging.exception("failed getting attribute %s from %s, "
                              "exception %s" % (self.attr, str(pkg), str(ae)))
            raise
        except Exception, e:
            logging.exception("caught unexpected exception accessing %s from %s, "
                         "exception %s" % (self.attr, str(pkg), str(e)))
            raise AttributeError(self.attr)

    def match(self, pkg):
        try:
            return self.restriction.match(self.__pull_attr(pkg)) != self.negate
        except AttributeError, ae:
            s = self.attr.split(".")
            if not any(x in s for x in ae.args):
                raise
            return self.negate

    def force_False(self, pkg):
        try:
            if self.negate:
                return self.restriction.force_True(pkg, self.attr,
                                                   self.__pull_attr(pkg))
            else:
                return self.restriction.force_False(pkg, self.attr,
                                                    self.__pull_attr(pkg))
        except AttributeError, ae:
            s = self.attr.split('.')
            if not any(x in s for x in ae.args):
                raise
            return not self.negate

    def force_True(self, pkg):
        try:
            if self.negate:
                return self.restriction.force_False(pkg, self.attr,
                                                    self.__pull_attr(pkg))
            else:
                return self.restriction.force_True(pkg, self.attr,
                                                   self.__pull_attr(pkg))
        except AttributeError, ae:
            s = self.attr.split('.')
            if not any(x in s for x in ae.args):
                raise
            return self.negate

    def __len__(self):
        if not isinstance(self.restriction, boolean.base):
            return 1
        return len(self.restriction) + 1

    def intersect(self, other):
        """Build a restriction that matches anything matched by this and other.

        If an optimized intersection cannot be determined this returns C{None}.
        """
        if (self.negate != other.negate or
            self.attr != other.attr or
            self.__class__ is not other.__class__):
            return None
        # Make the most subclassed instance do the intersecting
        if isinstance(self.restriction, other.restriction.__class__):
            s = self.restriction.intersect(other.restriction)
        elif isinstance(other.restriction, self.restriction.__class__):
            s = other.restriction.intersect(self.restriction)
        else:
            # Child restrictions are not related, give up.
            return None
        if s is None:
            return None

        # optimization: do not build a new wrapper if we already have one.
        if s == self.restriction:
            return self
        elif s == other.restriction:
            return other

        # This breaks completely if we are a subclass with different
        # __init__ args, so such a subclass had better override this
        # method...
        return self.__class__(self.attr, s, negate=self.negate)

    def __eq__(self, other):
        if self is other:
            return True
        return (
            self.__class__ is other.__class__ and
            self.negate == other.negate and
            self.attr == other.attr and
            self.restriction == other.restriction)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.negate, self.attr, self.restriction))

    def __str__(self):
        s = self.attr+" "
        if self.negate:
            s += "not "
        return s + str(self.restriction)

    def __repr__(self):
        if self.negate:
            string = '<%s attr=%r restriction=%r negated @%#8x>'
        else:
            string = '<%s attr=%r restriction=%r @%#8x>'
        return string % (
            self.__class__.__name__, self.attr, self.restriction, id(self))


class Conditional(PackageRestriction):

    """
    base object representing a conditional package restriction

    used to control whether a payload of restrictions are accessible or not
    """

    __slots__ = ("payload",)

    __inst_caching__ = True

    def __init__(self, attr, childrestriction, payload, **kwds):
        """
        n@param attr: attr to match against
        @param childrestriction: restriction to control whether or not the
            payload is accessible
        @param payload: payload data, whatever it may be.
        @param kwds: additional args to pass to L{PackageRestriction}
        """
        super(Conditional, self).__init__(attr, childrestriction, **kwds)
        object.__setattr__(self, "payload", tuple(payload))

    def intersect(self, other):
        # PackageRestriction defines this but its implementation won't
        # work for us, so fail explicitly.
        raise NotImplementedError(self)

    def __str__(self):
        return "( Conditional: %s payload: [ %s ] )" % (
            PackageRestriction.__str__(self),
            ", ".join(map(str, self.payload)))

    def __repr__(self):
        if self.negate:
            string = '<%s attr=%r restriction=%r payload=%r negated @%#8x>'
        else:
            string = '<%s attr=%r restriction=%r payload=%r @%#8x>'
        return string % (
            self.__class__.__name__, self.attr, self.restriction, self.payload,
            id(self))

    def __iter__(self):
        return iter(self.payload)

    def __hash__(self):
        return hash((self.attr, self.negate, self.restriction, self.payload))

    def __eq__(self, other):
        if self is other:
            return True
        return (
            self.__class__ is other.__class__ and
            self.negate == other.negate and
            self.attr == other.attr and
            self.restriction == other.restriction
            and self.payload == other.payload)


# "Invalid name" (pylint uses the module const regexp, not the class regexp)
# pylint: disable-msg=C0103

AndRestriction = restriction.curry_node_type(boolean.AndRestriction,
                                             restriction.package_type)
OrRestriction = restriction.curry_node_type(boolean.OrRestriction,
                                            restriction.package_type)

AlwaysBool = restriction.curry_node_type(restriction.AlwaysBool,
                                         restriction.package_type)

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
