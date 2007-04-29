# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.containers import RefCountingSet
from pkgcore.resolver.pigeonholes import PigeonHoledSlots

REMOVE  = 0
ADD     = 1
REPLACE = 2
FORWARD_BLOCK_INCREF = 3
FORWARD_BLOCK_DECREF = 4

class plan_state(object):
    def __init__(self):
        self.state = PigeonHoledSlots()
        self.plan = []
        self.pkg_choices = {}
        self.rev_blockers = {}
        self.blockers_refcnt = RefCountingSet()
        self.match_atom = self.state.find_atom_matches

    def add_blocker(self, choices, blocker, key=None):
        """adds blocker, returning any packages blocked"""
        return incref_forward_block_op(choices, blocker, key).apply(self)

    def _remove_pkg_blockers(self, choices):
        l = self.rev_blockers.get(choices, ())
        for blocker, key in l:
            decref_forward_block_op(choices, blocker, key).apply(self)

    def backtrack(self, state_pos):
        assert state_pos <= len(self.plan)
        if len(self.plan) == state_pos:
            return
        for change in reversed(self.plan[state_pos:]):
            change.revert(self)
        self.plan = self.plan[:state_pos]

    def iter_ops(self, return_livefs=False):
        iterable = (x for x in self.plan if not x.internal)
        if return_livefs:
            return iterable
        return (y for y in iterable
            if not y.pkg.repo.livefs)

    @property
    def current_state(self):
        return len(self.plan)


class base_op(object):
    __slots__ = ("pkg", "force", "choices")
    internal = False

    def __init__(self, choices, pkg, force=False):
        self.choices = choices
        self.pkg = pkg
        self.force = force

    def __str__(self):
        s = ''
        if self.force:
            s = ' forced'
        return "%s: %s%s" % (self.desc, self.pkg, s)


class add_op(base_op):

    desc = "add"

    def apply(self, plan):
        l = plan.state.fill_slotting(self.pkg, force=self.force)
        if l and not self.force:
            return l
        plan.pkg_choices[self.pkg] = self.choices
        plan.plan.append(self)

    def revert(self, plan):
        plan.state.remove_slotting(self.pkg)
        del plan.pkg_choices[self.pkg]


class remove_op(base_op):
    __slots__ = ()

    desc = "remove"

    def apply(self, plan):
        plan.state.remove_slotting(self.pkg)
        plan._remove_pkg_blockers(plan.pkg_choices)
        del plan.pkg_choices[self.pkg]
        plan.plan.append(self)

    def revert(self, plan):
        plan.state.fill_slotting(self.pkg, force=self.force)
        plan.pkg_choices[self.pkg] = self.choices


class replace_op(base_op):
    __slots__ = ("old_pkg", "old_choices")

    desc = "replace"

    def apply(self, plan):
        old = plan.state.get_conflicting_slot(self.pkg)
        # probably should just convert to an add...
        assert old is not None
        plan.state.remove_slotting(old)
        old_choices = plan.pkg_choices[old]
        revert_point = plan.current_state
        plan._remove_pkg_blockers(old_choices)
        l = plan.state.fill_slotting(self.pkg, force=self.force)
        if l:
            # revert... limiter.
            l2 = plan.state.fill_slotting(old)
            plan.backtrack(revert_point)
            assert not l2
            return l

        # wipe olds blockers.

        self.old_pkg = old
        self.old_choices = old_choices
        del plan.pkg_choices[old]
        plan.pkg_choices[self.pkg] = self.choices
        plan.plan.append(self)

    def revert(self, plan):
        # far simpler, since the apply op generates multiple ops on it's own.
        # all we have to care about is swap.
        plan.state.remove_slotting(self.pkg)
        l = plan.state.fill_slotting(self.old_pkg, force=self.force)
        assert not l
        del plan.pkg_choices[self.pkg]
        plan.pkg_choices[self.old_pkg] = self.old_choices

    def __str__(self):
        s = ''
        if self.force:
            s = ' forced'
        return "replace: %s with %s%s" % (self.old_pkg, self.pkg, s)


class blocker_base_op(object):
    __slots__ = ("choices", "blocker", "key")

    desc = None
    internal = True

    def __init__(self, choices, blocker, key=None):
        if key is None:
            self.key = blocker.key
        else:
            self.key = key
        self.choices = choices
        self.blocker = blocker

    def __str__(self):
        return "%s: key %s, %s from %s" % (self.__class__.__name__, self.key,
            self.blocker, self.choices)


class incref_forward_block_op(blocker_base_op):
    __slots__ = ()

    def apply(self, plan):
        plan.plan.append(self)
        if self.blocker not in plan.blockers_refcnt:
            l = plan.state.add_limiter(self.blocker, self.key)
            plan.rev_blockers.setdefault(self.choices, []).append(
                (self.blocker, self.key))
        else:
            l = []
        plan.blockers_refcnt.add(self.blocker)
        return l

    def revert(self, plan):
        l = plan.rev_blockers[self.choices]
        l.remove((self.blocker, self.key))
        if not l:
            del plan.rev_blockers[self.choices]
        plan.blockers_refcnt.remove(self.blocker)
        if self.blocker not in plan.blockers_refcnt:
            plan.state.remove_limiter(self.blocker, self.key)


class decref_forward_block_op(blocker_base_op):
    __slots__ = ()

    def apply(self, plan):
        plan.plan.append(self)
        plan.blockers_refcnt.remove(self.blocker)
        if self.blocker not in plan.blockers_refcnt:
            plan.state.remove_limiter(self.blocker, self.key)
        plan.rev_blockers[self.choices].remove((self.blocker, self.key))
        if not plan.rev_blockers[self.choices]:
            del plan.rev_blockers[self.choices]

    def revert(self, plan):
        plan.rev_blockers.setdefault(self.choices, []).append(
            (self.blocker, self.key))
        if self.blocker not in plan.blockers_refcnt:
            plan.state.add_limiter(self.blocker, self.key)
        plan.blockers_refcnt.add(self.blocker)
