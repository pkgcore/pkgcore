# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.restrictions import restriction

# lil too getter/setter like for my tastes...

class PigeonHoledSlots(object):
    """class for tracking slotting to a specific atom/obj key
    no atoms present, just prevents conflicts of obj.key; atom present, assumes
    it's a blocker and ensures no obj matches the atom for that key
    """

    def __init__(self):
        self.slot_dict = {}

    def fill_slotting(self, obj, force=False):
        """Try to insert obj in.

        @return: any conflicting objs (empty list if inserted successfully).
        """
        key = obj.key
        l = []
        for x in self.slot_dict.setdefault(key, []):
            if isinstance(x, restriction.base):
                if x.match(obj):
                    # no go.  blocker.
                    l.append(x)
            else:
                if x.slot == obj.slot:
                    l.append(x)
        if not l or force:
            self.slot_dict[key].append(obj)
        return l

    def get_conflicting_slot(self, pkg):
        for x in self.slot_dict.get(pkg.key, []):
            if not isinstance(x, restriction.base) and pkg.slot == x.slot:
                return x
        return None

    def find_key_matches(self, key):
        return [
            x for x in self.slot_dict.get(key, [])
            if not isinstance(x, restriction.base)]

    def find_atom_matches(self, atom):
        return [x for x in self.find_key_matches(atom.key) if atom.match(x)]

    def add_limiter(self, atom, key=None):
        """add a limiter, returning any conflicting objs"""
        if not isinstance(atom, restriction.base):
            raise TypeError("atom must be a restriction.base derivative")
        # debug.

        if key is None:
            key = atom.key
        l = []
        for x in self.slot_dict.setdefault(key, []):
            if not isinstance(x, restriction.base) and atom.match(x):
                l.append(x)

        self.slot_dict[key].append(atom)
        return l

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
        l = [x for x in self.slot_dict[key] if x is not atom]
        if not l:
            del self.slot_dict[key]

    def __contains__(self, obj):
        for o in self.slot_dict[obj.key]:
            if o == obj:
                return True
        return False
