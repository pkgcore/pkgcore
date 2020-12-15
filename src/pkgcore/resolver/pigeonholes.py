__all__ = ("PigeonHoledSlots",)

from ..restrictions import restriction

# lil too getter/setter like for my tastes...


class PigeonHoledSlots:
    """class for tracking slotting to a specific atom/obj key
    no atoms present, just prevents conflicts of obj.key; atom present, assumes
    it's a blocker and ensures no obj matches the atom for that key
    """

    def __init__(self):
        self.slot_dict = {}
        self.limiters = {}

    def fill_slotting(self, obj, force=False):
        """Try to insert obj in.

        :return: any conflicting objs (empty list if inserted successfully).
        """

        l = self.check_limiters(obj)

        key = obj.key
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
        return list(filter(atom.match, self.slot_dict.get(key, ())))

    def add_limiter(self, atom, key=None):
        """add a limiter, returning any conflicting objs"""
        if not isinstance(atom, restriction.base):
            raise TypeError(
                f"atom must be a restriction.base derivative: got {atom!r}, key={key!r}")
        # debug.

        if key is None:
            key = atom.key
        self.limiters.setdefault(key, []).append(atom)
        return self.find_atom_matches(atom, key=key)

    def check_limiters(self, obj):
        """return any limiters conflicting w/ the passed in obj"""
        key = obj.key
        return [x for x in self.limiters.get(key, ()) if x.match(obj)]

    def remove_slotting(self, obj):
        key = obj.key
        # let the key error be thrown if they screwed up.
        slots = self.slot_dict.get(key, ())
        l = [x for x in slots if x is not obj]
        if len(l) == len(slots):
            raise KeyError(f"obj {obj} isn't slotted")
        if l:
            self.slot_dict[key] = l
        else:
            del self.slot_dict[key]

    def remove_limiter(self, atom, key=None):
        if key is None:
            key = atom.key
        l = [x for x in self.limiters[key] if x is not atom]
        if len(l) == len(self.limiters[key]):
            raise KeyError(f"obj {atom} isn't slotted")
        if not l:
            del self.limiters[key]
        else:
            self.limiters[key] = l

    def __contains__(self, obj):
        if isinstance(obj, restriction.base):
            return obj in self.limiters.get(obj.key, ())
        return obj in self.slot_dict.get(obj.key, ())
