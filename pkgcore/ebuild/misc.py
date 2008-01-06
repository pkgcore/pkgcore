# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
misc. stuff we've not found a spot for yet.
"""

from pkgcore.restrictions import packages, restriction
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.profiles import incremental_expansion

from snakeoil.lists import iflatten_instance
from snakeoil.klass import generic_equality

class collapsed_restrict_to_data(object):

    __metaclass__ = generic_equality
    __attr_comparison__ = ('defaults', 'freeform', 'atoms', '__class__')

    def __init__(self, *restrict_sources):
        """
        descriptive, no?

        Basically splits an iterable of restrict:data into
        level of specificity, repo, cat, pkg, atom (dict) for use
        in filters
        """

        always = []
        repo = []
        cat = []
        pkg = []
        atom_d = {}
        for restrict_pairs in restrict_sources:
            for a, data in restrict_pairs:
                if not data:
                    continue
                if isinstance(a, restriction.AlwaysBool):
                    # yes, odd attr name, but negate holds the val to return.
                    # note also, we're dropping AlwaysFalse; it'll never match.
                    if a.negate:
                        always.extend(data)
                        for atomlist in atom_d.itervalues():
                            atomlist.append((a, set([flag for flag in data if flag.startswith("-")])))
                elif isinstance(a, atom):
                    atom_d.setdefault(a.key, []).append((a, data))
                elif isinstance(a, packages.PackageRestriction):
                    if a.attr == "category":
                        cat.append((a, data))
                    elif a.attr == "package":
                        pkg.append((a, data))
                    else:
                        raise ValueError("%r doesn't operate on package/category: "
                            "data %r" % (a, data))
                elif isinstance(a, restriction.AlwaysBool):
                    repo.append((a, data))
                else:
                    raise ValueError("%r is not a AlwaysBool, PackageRestriction, "
                        "or atom: data %r" % (a, data))

        if always:
            s = set()
            incremental_expansion(s, always)
            always = s
        else:
            always = set()
        self.defaults = always
        self.freeform = tuple(x for x in (repo, cat, pkg) if x)
        self.atoms = atom_d

    def atom_intersects(self, atom):
        return atom.key in self.atoms

    def pull_data(self, pkg, force_copy=False):
        l = []
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    l.append(data)
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)
        if not l:
            if force_copy:
                return set(self.defaults)
            return self.defaults
        s = set(self.defaults)
        incremental_expansion(s, iflatten_instance(l))
        return s

    def pull_cp_data(self, pkg, force_copy=False):
        """pull cp-related data"""
        enabled_flags = set()
        disabled_flags = set()
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                for entry in data:
                    if entry.startswith("-"):
                        enabled_flags.discard(entry[1:])
                        disabled_flags.add(entry[1:])
                    else:
                        disabled_flags.discard(entry)
                        enabled_flags.add(entry)
        return enabled_flags, disabled_flags

    def iter_pull_data(self, pkg):
        for item in self.defaults:
            yield item
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    for item in data:
                        yield item
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                for item in data:
                    yield item


class non_incremental_collapsed_restrict_to_data(collapsed_restrict_to_data):

    def pull_data(self, pkg, force_copy=False):
        l = []
        for specific in self.freeform:
            for restrict, data in specific:
                if restrict.match(pkg):
                    l.append(data)
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)
        if not l:
            if force_copy:
                return set(self.defaults)
            return self.defaults
        s = set(self.defaults)
        s.update(iflatten_instance(l))
        return s

    def iter_pull_data(self, pkg):
        l = [self.defaults]
        for specific in self.freeform:
            l.extend(data for restrict, data in specific if restrict.match(pkg))
        for atom, data in self.atoms.get(pkg.key, ()):
            if atom.match(pkg):
                l.append(data)
        if len(l) == 1:
            return iter(self.defaults)
        return iflatten_instance(l)
