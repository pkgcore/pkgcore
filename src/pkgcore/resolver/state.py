__all__ = (
    "plan_state", "base_op_state", "add_op", "add_hardref_op",
    "add_backref_op", "remove_op", "replace_op", "blocker_base_op",
    "incref_forward_block_op", "decref_forward_block_op",
)

from snakeoil.containers import RefCountingSet

from .pigeonholes import PigeonHoledSlots


class plan_state:

    def __init__(self):
        self.state = PigeonHoledSlots()
        self.plan = []
        self.pkg_choices = {}
        self.rev_blockers = {}
        self.blockers_refcnt = RefCountingSet()
        self.match_atom = self.state.find_atom_matches
        self.vdb_filter = set()
        self.forced_restrictions = RefCountingSet()

    def add_blocker(self, choices, blocker, key=None):
        """Adds blocker, returning any packages blocked.

        :param choices: package choices
        :type choices: :obj:`pkgcore.resolver.choice_point.choice_point`
        """
        return incref_forward_block_op(choices, blocker, key).apply(self)

    def _remove_pkg_blockers(self, choices):
        """Remove blockers.

        :param choices: package choices
        :type choices: :obj:`pkgcore.resolver.choice_point.choice_point`
        """
        l = self.rev_blockers.get(choices, ())
        # walk a copy- it's possible it'll change under foot
        for blocker, key in l[:]:
            decref_forward_block_op(choices, blocker, key).apply(self)

    def backtrack(self, state_pos):
        """Backtrack over a plan."""
        assert state_pos <= len(self.plan)
        if len(self.plan) == state_pos:
            return

        # track exactly how many reversions we've done-
        # since we do a single slicing of plan, if an exception occurs
        # before finishing we need to prune what has been finished,
        # and just that.
        reversion_count = 0
        try:
            for reversion_count, change in enumerate(reversed(self.plan[state_pos:])):
                change.revert(self)
            reversion_count += 1
            assert len(self.plan) - reversion_count == state_pos
        finally:
            if reversion_count:
                self.plan = self.plan[:-reversion_count]

    def iter_ops(self, return_livefs=False):
        iterable = (x for x in self.plan if not x.internal)
        if return_livefs:
            return iterable
        return (y for y in iterable
            if not y.pkg.repo.livefs or y.desc == 'remove')

    def ops(self, livefs=False, only_real=False):
        i = self.iter_ops(livefs)
        if only_real:
            i = (x for x in i if x.pkg.package_is_real)
        return ops_sequence(i)

    def __getitem__(self, slice):
        return self.plan[slice]

    @property
    def current_state(self):
        return len(self.plan)


class ops_sequence:

    def __init__(self, sequence, is_livefs=True):
        self._ops = tuple(sequence)
        self.is_livefs = is_livefs

    def __getitem__(self, *args):
        return self._ops.__getitem__(*args)

    def __len__(self):
        return len(self._ops)

    def __iter__(self):
        return iter(self._ops)

    def __bool__(self):
        return bool(self._ops)


class base_op_state:

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

    def __repr__(self):
        return '<%s choices=%r pkg=%r force=%s @#%x>' % (
            self.__class__.__name__, self.choices, self.pkg, self.force,
            id(self))

    def apply(self, plan):
        raise NotImplemented(self, 'apply')

    def revert(self, plan):
        raise NotImplemented(self, 'revert')


class add_op(base_op_state):

    __slots__ = ()
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


class add_hardref_op(base_op_state):

    __slots__ = ('restriction',)
    desc = "hardref"
    internal = True
    force = True
    choices = None
    pkg = None

    def __init__(self, restriction):
        self.restriction = restriction

    def apply(self, plan):
        plan.plan.append(self)
        plan.forced_restrictions.add(self.restriction)

    def revert(self, plan):
        plan.forced_restrictions.remove(self.restriction)


class add_backref_op(base_op_state):

    __slots__ = ()
    desc = "backref"
    internal = True

    def apply(self, plan):
        plan.plan.append(self)
        pass

    def revert(self, plan):
        pass


class remove_op(base_op_state):

    __slots__ = ()
    desc = "remove"

    def apply(self, plan):
        plan.state.remove_slotting(self.pkg)
        plan._remove_pkg_blockers(self.choices)
        del plan.pkg_choices[self.pkg]
        plan.plan.append(self)
        plan.vdb_filter.add(self.pkg)

    def revert(self, plan):
        plan.state.fill_slotting(self.pkg, force=True)
        plan.pkg_choices[self.pkg] = self.choices
        plan.vdb_filter.remove(self.pkg)


class replace_op(base_op_state):

    __slots__ = ("old_pkg", "old_choices", "force_old")
    desc = "replace"

    def __init__(self, *args, **kwds):
        base_op_state.__init__(self, *args, **kwds)
        self.old_pkg, self.old_choices = None, None
        self.force_old = False

    def apply(self, plan):
        revert_point = plan.current_state
        old = plan.state.get_conflicting_slot(self.pkg)
        # probably should just convert to an add...
        force_old = bool(plan.state.check_limiters(old))
        assert old is not None
        plan.state.remove_slotting(old)
        old_choices = plan.pkg_choices[old]
        # assertion for my own sanity...
        assert revert_point == plan.current_state
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
        self.force_old = force_old
        self.old_choices = old_choices
        del plan.pkg_choices[old]
        plan.pkg_choices[self.pkg] = self.choices
        plan.plan.append(self)
        plan.vdb_filter.add(old)

    def revert(self, plan):
        # far simpler, since the apply op generates multiple ops on its own.
        # all we have to care about is swap.
        plan.state.remove_slotting(self.pkg)
        l = plan.state.fill_slotting(self.old_pkg, force=self.force_old)
        if bool(l) != self.force_old:
            raise AssertionError(
                "Internal error detected, unable to revert %s; got %s, "
                "force_old=%s " % (self, l, self.force_old))
        del plan.pkg_choices[self.pkg]
        plan.pkg_choices[self.old_pkg] = self.old_choices
        plan.vdb_filter.remove(self.old_pkg)

    def __str__(self):
        s = ''
        if self.force:
            s = ' forced'
        return "replace: %s with %s%s" % (self.old_pkg, self.pkg, s)

    def __repr__(self):
        return '<%s old choices=%r new choices=%r old_pkg=%r new_pkg=%r ' \
            'force=%s @#%x>' % (self.__class__.__name__, self.old_choices,
            self.choices, self.old_pkg, self.pkg, self.force, id(self))


class blocker_base_op:

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

    def __repr__(self):
        return '<%s choices=%r blocker=%r key=%r @#%x>' % (
            self.__class__.__name__, self.choices, self.blocker, self.key,
            id(self))

    def apply(self, plan):
        raise NotImplementedError(self, 'apply')

    def revert(self, plan):
        raise NotImplementedError(self, 'revert')


class incref_forward_block_op(blocker_base_op):

    __slots__ = ()

    def apply(self, plan):
        plan.plan.append(self)
        if self.blocker not in plan.blockers_refcnt:
            l = plan.state.add_limiter(self.blocker, self.key)
        else:
            l = []
        plan.rev_blockers.setdefault(self.choices, []).append(
             (self.blocker, self.key))
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
