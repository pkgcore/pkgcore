# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
functionality to collapse O(N) restriction match calls into ~O(1)
"""

__all__ = ("DictBased")
from pkgcore.restrictions import restriction
from pkgcore.restrictions import packages

class DictBased(restriction.base):

    """
    Restrictions are (by default) executed in a depth/breadth method; for long chains of restrictions,
    this grows inneficient.  For example, package.mask'ing has over 300 atoms, effectively over 1800 objects in use.

    Running the filter on each package instance returned from a repo would be exceedingly slow, a way to get as close to
    constant lookup as possible is needed.

    DictBased works by using supplied functions to collapse long chains of restrictions into a dict, with key
    defined by get_key_from_package, and with the value of that key holding the remaining restrictions (if any).

    Common usage at this point is to collapse category and package attribute restrictions into constant lookup, with
    any remaining version restrictions being handed off as a val.

    Example usage of this class should be available in pkgcore.ebuild.domain

    Aside from that, method of generating keys/collapsing restrictions is subject to change, still need to push metadata
    in re: what restriction types are being collapsed; short version, api isn't declared stable yet.
    """

    __slots__ = ("restricts_dict", "get_pkg_key", "get_atom_key")
    type = packages.package_type
    inst_caching = False

    def __init__(self, restriction_items, get_key_from_package, *args, **kwargs):
        """
        
        @param restriction_items: source of restriction keys and remaining restriction (if none, set it to None)
        @param get_key_from_package: is a function to get the key from a pkg instance
        @param args: pass any additional args to L{pkgcore.restrictions.restriction.base}
        @param kwargs: pass any additional args to L{pkgcore.restrictions.restriction.base}
        """

        if not callable(get_key_from_package):
            raise TypeError(get_key_from_package)

        super(DictBased, self).__init__(*args, **kwargs)
        self.restricts_dict = {}
        for key, restrict in restriction_items:
            if not restrict:
                restrict = packages.AlwaysTrue

            if key in self.restricts_dict:
                self.restricts_dict[key].add_restriction(restrict)
            else:
                self.restricts_dict[key] = packages.OrRestriction(restrict, inst_caching=False)

        self.get_pkg_key = get_key_from_package


    def match(self, pkginst):
        try:
            key = self.get_pkg_key(self, pkginst)
        except (TypeError, AttributeError):
            return self.negate
        if key not in self.restricts_dict:
            return self.negate

        remaining = self.restricts_dict[key]
        return remaining.match(pkginst) != self.negate

#	def __contains__(self, restriction):
#		if isinstance(restriction, base):
#			key, r = self.get_atom_key(restriction)
#		if key is not None and key in self.restricts_dict:
#			return True
#		return False

    def __str__(self):
        return "%s: pkg_key(%s), " % (self.__class__, self.get_pkg_key)
