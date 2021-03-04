from snakeoil.test import TestCase

from pkgcore.resolver.pigeonholes import PigeonHoledSlots
from pkgcore.restrictions import restriction

from .test_choice_point import fake_package


class fake_blocker(restriction.base):

    __slots__ = ('key', 'blocks')

    def __init__(self, key, blocks=()):
        restriction.base.__init__(self)
        if not isinstance(blocks, (list, tuple)):
            blocks = [blocks]
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "blocks", blocks)

    def __str__(self):
        return f"fake_atom({self.key}, {self.blocks})"

    def match(self, obj):
        for x in self.blocks:
            if x is obj:
                return True
        return False

class SlotTesting(TestCase):

    def test_add(self):
        c = PigeonHoledSlots()
        o = fake_package()
        self.assertEqual([], c.fill_slotting(o))
        # test that it doesn't invalidly block o when (innefficiently)
        # doing a re-add
        self.assertEqual([o], c.fill_slotting(o))
        self.assertEqual([o], c.fill_slotting(fake_package()))
        self.assertFalse(c.fill_slotting(fake_package(slot=1, key=1)))

    def test_add_limiter(self):
        c = PigeonHoledSlots()
        p = fake_package()
        o = fake_blocker(None, p)
        self.assertFalse([], c.fill_slotting(p))
        self.assertEqual([p], c.add_limiter(o))
        c.remove_slotting(p)
        self.assertEqual([o], c.fill_slotting(p))
        # note we're doing 'is' tests in fake_blocker
        self.assertFalse([], c.fill_slotting(fake_package()))

    def test_remove_slotting(self):
        c = PigeonHoledSlots()
        p, p2 = fake_package(), fake_package(slot=2)
        o = fake_blocker(None, p)
        self.assertFalse([], c.add_limiter(o))
        c.remove_limiter(o)
        self.assertRaises(KeyError, c.remove_slotting, o)
        self.assertRaises(KeyError, c.remove_limiter, o)
        self.assertFalse([], c.fill_slotting(p))
        self.assertFalse([], c.fill_slotting(p2))
        c.remove_slotting(p)
        c.remove_slotting(p2)
