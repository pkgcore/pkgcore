# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.restrictions import restriction

# lil too getter/setter like for my tastes...

class PigeonHoledSlots(object):
    """class for tracking slotting to a specific atom/obj key
    no atoms present, just prevents conflicts of obj.key; atom present, assumes
    it's a blocker and ensures no obj matches the atom for that key
    """

    def __init__(self):
        self.slot_dict = {}
        self.limiters = {}

    def fill_slotting(self, obj, force=False):
        """Try to insert obj in.

        @return: any conflicting objs (empty list if inserted successfully).
        """
        key = obj.key
        l = [x for x in self.limiters.get(key, ()) if x.match(obj)]

        dslot = obj.slot
        l.extend(x for x in self.slot_dict.get(key, ()) if x.slot == dslot)

        if not l or force:
            self.slot_dict.setdefault(key, []).append(obj)
        return l


    def get_conflicting_slot(self, pkg):
        for x in self.slot_dict.get(pkg.key, ()):
            if pkg.slot == x.slot:
                return x
        return None

    def find_atom_matches(self, atom, key=None):
        if key is None:
            key = atom.key
        return filter(atom.match, self.slot_dict.get(key, ()))

    def add_limiter(self, atom, key=None):
        """add a limiter, returning any conflicting objs"""
        if not isinstance(atom, restriction.base):
            raise TypeError("atom must be a restriction.base derivative: "
                "got %r, key=%r" % (atom, key))
        # debug.

        if key is None:
            key = atom.key
        self.limiters.setdefault(key, []).append(atom)
        return filter(atom.match, self.slot_dict.get(key, ()))

    def remove_slotting(self, obj):
        key = obj.key
        # let the key error be thrown if they screwed up.
        l = [x for x in self.slot_dict[key] if x is not obj]
        if len(l) == len(self.slot_dict[key]):
            raise KeyError("obj %s isn't slotted" % obj)
        if l:
            self.slot_dict[key] = l
        else:
            del self.slot_dict[key]

    def remove_limiter(self, atom, key=None):
        if key is None:
            key = atom.key
        l = [x for x in self.limiters[key] if x is not atom]
        if len(l) == len(self.limiters[key]):
            raise KeyError("obj %s isn't slotted" % atom)
        if not l:
            del self.limiters[key]
        else:
            self.limiters[key] = l

    def __contains__(self, obj):
        if isinstance(obj, restriction.base):
            return obj in self.limiters.get(obj.key, ())
        return obj in self.slot_dict.get(obj.key, ())
