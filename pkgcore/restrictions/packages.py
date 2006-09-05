# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
restriction classes designed for package level matching
"""

import operator
from pkgcore.util.currying import pre_curry, pretty_docs
from pkgcore.restrictions import restriction, boolean
from pkgcore.util.demandload import demandload
demandload(globals(), "logging")

# Backwards compatibility.
package_type = restriction.package_type


class PackageRestriction(restriction.base):

    """Package data restriction."""

    # Careful: some methods (__eq__, __hash__, intersect) try to work
    # for subclasses too. They will not behave as intended if a
    # subclass adds attributes. So if you do that, override the
    # methods.

    __slots__ = ("attr_split", "attr", "restriction")
    type = restriction.package_type
    subtype = restriction.value_type
    __inst_caching__ = True

    def __init__(self, attr, restriction, negate=False):
        """
        @param attr: package attribute to match against
        @param restriction: a L{pkgcore.restrictions.values.base} instance to pass attr to for matching
        @param negate: should the results be negated?
        """
        super(PackageRestriction, self).__init__(negate=negate)
        self.attr_split = tuple(operator.attrgetter(x)
                                for x in attr.split("."))
        self.attr = attr
        if not restriction.type == self.subtype:
            raise TypeError("restriction must be of type %r" % (self.subtype,))
        self.restriction = restriction

    def __pull_attr(self, pkg):
        try:
            o = pkg
            for f in self.attr_split:
                o = f(o)
            return o
        except (KeyboardInterrupt, RuntimeError, SystemExit):
            raise
        except AttributeError,ae:
            logging.debug("failed getting attribute %s from %s, "
                          "exception %s" % (self.attr, str(pkg), str(ae)))
            raise
        except Exception, e:
            logging.warn("caught unexpected exception accessing %s from %s, "
                         "exception %s" % (self.attr, str(pkg), str(e)))
            raise AttributeError(self.attr)

    def match(self, pkg):
        try:
            return self.restriction.match(self.__pull_attr(pkg)) != self.negate
        except AttributeError:
            return self.negate


    def force_False(self, pkg):
        if self.negate:
            return self.restriction.force_True(pkg, self.attr,
                                               self.__pull_attr(pkg))
        else:
            return self.restriction.force_False(pkg, self.attr,
                                                self.__pull_attr(pkg))

    def force_True(self, pkg):
        if self.negate:
            return self.restriction.force_False(pkg, self.attr,
                                                self.__pull_attr(pkg))
        else:
            return self.restriction.force_True(pkg, self.attr,
                                               self.__pull_attr(pkg))

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

    def __init__(self, attr, restriction, payload, **kwds):
        """
        @param attr: attr to match against
        @param restriction: restriction to control whether or not the payload is accessible
        @param payload: payload data, whatever it may be.
        @param kwds: additional args to pass to L{PackageRestriction}
        """
        super(Conditional, self).__init__(attr, restriction, **kwds)
        self.payload = tuple(payload)

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


for m, l in [[boolean, ["AndRestriction", "OrRestriction", "XorRestriction"]],
             [restriction, ["AlwaysBool"]]]:
    for x in l:
        o = getattr(m, x)
        doc = o.__doc__
        o = pre_curry(o, node_type=restriction.package_type)
        if doc is None:
            doc = ''
        else:
            # do this so indentation on pydoc __doc__ is sane
            doc = "\n".join(x.lstrip() for x in doc.split("\n")) +"\n"
            doc += "Automatically set to package type"
        globals()[x] = pretty_docs(o, doc)

del x, m, l, o, doc

AlwaysTrue = AlwaysBool(negate=True)
AlwaysFalse = AlwaysBool(negate=False)
