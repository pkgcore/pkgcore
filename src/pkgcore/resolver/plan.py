__all__ = ("resolver_frame", "resolver_stack", "merge_plan")

import operator
import sys
from collections import deque
from functools import partial
from itertools import chain, filterfalse, islice

from snakeoil.compatibility import cmp, sort_cmp
from snakeoil.iterables import caching_iter

# XXX: hack; see insert_blockers
from ..ebuild import atom as _atom
from ..repository import filtered, misc, multiplex, util
from ..restrictions import packages, restriction, values
from . import state
from .choice_point import choice_point

limiters = set(["cycle"])


def dprint(handle, fmt, args=None, label=None):
    if None in limiters or label in limiters:
        if args:
            fmt = fmt % args
        handle.write(fmt)
        handle.write("\n")


# iter/pkg sorting functions for selection strategy
pkg_sort_highest = partial(sorted, reverse=True)
pkg_sort_lowest = sorted

pkg_grabber = operator.itemgetter(0)


def highest_iter_sort(l, pkg_grabber=pkg_grabber):
    """Sort a list of packages from highest to lowest and prefer livefs.

    :param l: list of packages
    :param pkg_grabber: function to use as an attrgetter
    :return: sorted list of packages
    """
    def f(x, y):
        c = cmp(x, y)
        if c:
            return c
        elif x.repo.livefs:
            if y.repo.livefs:
                return 0
            return 1
        elif y.repo.livefs:
            return -1
        return 0
    sort_cmp(l, f, key=pkg_grabber, reverse=True)
    return l


def downgrade_iter_sort(restrict, l, pkg_grabber=pkg_grabber):
    """Sort a list of packages from highest to lowest and prefer nonlivefs.

    :param l: list of packages
    :param pkg_grabber: function to use as an attrgetter
    :return: sorted list of packages
    """
    def f(x, y):
        c = cmp(x, y)
        if x.repo.livefs:
            if y.repo.livefs:
                return c
            return -1
        elif y.repo.livefs:
            return 1
        elif restrict.match(x):
            if restrict.match(y):
                return 1
            return -1
        elif restrict.match(y):
            return 1
        return c
    sort_cmp(l, f, key=pkg_grabber, reverse=True)
    return l


def lowest_iter_sort(l, pkg_grabber=pkg_grabber):
    """Sort a list of packages from lowest to highest.

    :param l: list of packages
    :param pkg_grabber: function to use as an attrgetter
    :return: sorted list of packages
    """
    def f(x, y):
        c = cmp(x, y)
        if c:
            return c
        elif x.repo.livefs:
            if y.repo.livefs:
                return 0
            return -1
        elif y.repo.livefs:
            return 1
        return 0
    sort_cmp(l, f, key=pkg_grabber)
    return l


class MutableContainmentRestriction(values.base):

    __slots__ = ('_blacklist', 'match')

    def __init__(self, blacklist):
        sf = object.__setattr__
        sf(self, '_blacklist', blacklist)
        sf(self, 'match', self._blacklist.__contains__)


class resolver_frame:

    __slots__ = ("parent", "atom", "choices", "mode", "start_point", "dbs",
        "depth", "drop_cycles", "__weakref__", "ignored", "vdb_limited",
        "events", "succeeded")

    def __init__(self, parent, mode, atom, choices, dbs, start_point, depth,
                 drop_cycles, ignored=False, vdb_limited=False):
        assert hasattr(dbs, 'itermatch')
        self.parent = parent
        self.atom = atom
        self.choices = choices
        self.dbs = dbs
        self.mode = mode
        self.start_point = start_point
        self.depth = depth
        self.drop_cycles = drop_cycles
        self.ignored = False
        self.vdb_limited = vdb_limited
        self.events = []
        self.succeeded = None

    def reduce_solutions(self, nodes):
        if isinstance(nodes, (list, tuple)):
            self.events.append(("reduce", nodes))
        else:
            self.events.append(("reduce", (nodes,)))
        return self.choices.reduce_atoms(nodes)

    def __str__(self):
        pkg = self.current_pkg
        if pkg is None:
            pkg = "exhausted"
        else:
            cpv = pkg.cpvstr
            pkg = getattr(pkg.repo, 'repo_id', None)
            if pkg is not None:
                pkg = f"{cpv}::{pkg}"
            else:
                pkg = str(pkg)
        if self.succeeded is not None:
            result = ": %s" % (self.succeeded and "succeeded" or "failed")
        else:
            result = ""
        return "frame%s: mode %r: atom %s: current %s%s%s%s" % \
            (result, self.mode, self.atom, pkg,
            self.drop_cycles and ": cycle dropping" or '',
            self.ignored and ": ignored" or '',
            self.vdb_limited and ": vdb limited" or '')

    @property
    def current_pkg(self):
        """Return the package related to the resolver frame."""
        try:
            return self.choices.current_pkg
        except IndexError:
            return None


class resolver_stack(deque):

    frame_klass = resolver_frame
    depth = property(len)
    current_frame = property(operator.itemgetter(-1))
    _filter_ignored = staticmethod(
        partial(filterfalse, operator.attrgetter("ignored")))

    # this *has* to be a property, else it creates a cycle.
    parent = property(lambda s:s)

    def __init__(self):
        self.events = []

    def __str__(self):
        return 'resolver stack:\n  %s' % '\n  '.join(str(x) for x in self)

    def __repr__(self):
        return '<%s: %r>' % (self.__class__.__name__,
            tuple(repr(x) for x in self))

    def add_frame(self, mode, atom, choices, dbs, start_point, drop_cycles, vdb_limited=False):
        if not self:
            parent = self
        else:
            parent = self[-1]
        frame = self.frame_klass(parent, mode, atom, choices, dbs, start_point,
            self.depth + 1, drop_cycles, vdb_limited=vdb_limited)
        self.append(frame)
        return frame

    def add_event(self, event):
        if not self:
            self.events.append(event)
        else:
            self[-1].events.append(event)

    def pop_frame(self, result):
        frame = self.pop()
        frame.succeeded = bool(result)
        frame.parent.events.append(frame)

    def slot_cycles(self, trg_frame, **kwds):
        pkg = trg_frame.current_pkg
        slot = pkg.slot
        key = pkg.key
        kwds['skip_trg_frame'] = True
        return (frame for frame in self._cycles(trg_frame, **kwds)
            if key == frame.current_pkg.key and slot == frame.current_pkg.slot)

    def _cycles(self, trg_frame, start=0, reverse=False, skip_trg_frame=True):
        if reverse:
            i = self._filter_ignored(reversed(self))
        else:
            i = self._filter_ignored(self)
        if start != 0:
            i = islice(i, start, None)
        if skip_trg_frame:
            return (frame for frame in i if frame is not trg_frame)
        return i

    def index(self, frame, start=0, stop=None):
        i = self
        if start != 0 or stop is not None:
            i = slice(i, start, stop)

        for idx, x in enumerate(self):
            if x == frame:
                return idx + start
        return -1


class merge_plan:

    vdb_restrict = packages.PackageRestriction("repo.livefs", values.EqualityMatch(True))

    def __init__(self, dbs, per_repo_strategy, global_strategy=None,
                 depset_reorder_strategy=None, process_built_depends=False,
                 drop_cycles=False, debug=False, debug_handle=None):
        if debug:
            if debug_handle is None:
                debug_handle = sys.stdout
            self._dprint = partial(dprint, debug_handle)
        else:
            # don't run debug func when debugging is disabled
            self._dprint = lambda *args, **kwargs: None

        if not isinstance(dbs, (util.RepositoryGroup, list, tuple)):
            dbs = [dbs]

        if global_strategy is None:
            global_strategy = self.default_global_strategy

        if depset_reorder_strategy is None:
            depset_reorder_strategy = self.default_depset_reorder_strategy

        self.depset_reorder = depset_reorder_strategy
        self.all_raw_dbs = [misc.caching_repo(x, per_repo_strategy) for x in dbs]
        self.all_dbs = global_strategy(self.all_raw_dbs)
        self.default_dbs = self.all_dbs

        self.state = state.plan_state()
        vdb_state_filter_restrict = MutableContainmentRestriction(self.state.vdb_filter)
        self.livefs_dbs = multiplex.tree(
            *[filtered.tree(x, vdb_state_filter_restrict)
                for x in self.all_raw_dbs if x.livefs])

        self.insoluble = set()
        self.vdb_preloaded = False
        self._ensure_livefs_is_loaded = \
            self._ensure_livefs_is_loaded_nonpreloaded
        self.drop_cycles = drop_cycles
        self.process_built_depends = process_built_depends
        self._debugging = debug
        if debug:
            self._rec_add_atom = partial(self._stack_debugging_rec_add_atom,
                self._rec_add_atom)
            self._debugging_depth = 0
            self._debugging_drop_cycles = False

    @property
    def forced_restrictions(self):
        return frozenset(self.state.forced_restrictions)

    def reset(self, point=0):
        self.state.backtrack(point)

    def notify_starting_mode(self, mode, stack):
        if mode == "pdepend":
            mode = 'prdepends'
        self._dprint(
            "%s:%s%s: started: %s",
            (mode, ' ' * ((stack.current_frame.depth * 2) + 12 - len(mode)),
                stack.current_frame.atom,
                stack.current_frame.choices.current_pkg)
            )

    def notify_trying_choice(self, stack, atom, choices):
        self._dprint(
            "choose for %s%s, %s",
            (stack.depth *2*" ", atom, choices.current_pkg))
        stack.add_event(('inspecting', choices.current_pkg))

    def notify_choice_failed(self, stack, atom, choices, msg, msg_args=()):
        stack[-1].events.append(("choice", str(choices.current_pkg), False, msg % msg_args))
        if msg:
            msg = ': %s' % (msg % msg_args)
        self._dprint(
            "choice for %s%s, %s failed%s",
            (stack.depth * 2 * ' ', atom, choices.current_pkg, msg))

    def notify_choice_succeeded(self, stack, atom, choices, msg='', msg_args=()):
        stack[-1].events.append(("choice", str(choices.current_pkg), True, msg))
        if msg:
            msg = ': %s' % (msg % msg_args)
        self._dprint(
            "choice for %s%s, %s succeeded%s",
            (stack.depth * 2 * ' ', atom, choices.current_pkg, msg))

    def notify_viable(self, stack, atom, viable, msg='', pre_solved=False):
        t_viable = viable and "processing" or "not viable"
        if pre_solved and viable:
            t_viable = "pre-solved"
        t_msg = msg and (" "+msg) or ''
        s=''
        if stack:
            s = " for %s " % (stack[-1].atom)
        self._dprint(
            "%s%s%s%s%s",
            (t_viable.ljust(13), "  "*stack.depth, atom, s, t_msg))
        stack.add_event(("viable", viable, pre_solved, atom, msg))

    def load_vdb_state(self):
        for pkg in self.livefs_dbs:
            self._dprint("inserting %s", (pkg,), "vdb")
            ret = self.add_atom(pkg.versioned_atom)
            self._dprint("insertion of %s: %s", (pkg, ret), "vdb")
            if ret:
                raise Exception(
                    "couldn't load vdb state, %s %s" %
                    (pkg.versioned_atom, ret))
        self.vdb_preloaded = True
        self._ensure_livefs_is_loaded = \
            self._ensure_livefs_is_loaded_preloaded

    def add_atoms(self, restricts, finalize=False):
        if restricts:
            stack = resolver_stack()
            for restrict in restricts:
                state.add_hardref_op(restrict).apply(self.state)
            dbs = self.default_dbs
            for restrict in restricts:
                ret = self._add_atom(restrict, stack, dbs)
                if ret:
                    return ret
        if finalize:
            # note via this being outside the recursion, backtracking
            # is excluded... inline it somehow.
            self.process_finalize()
        return ()

    def process_finalize(self):
        pass

    def add_atom(self, atom):
        """add an atom, recalculating as necessary.

        :return: the last unresolvable atom stack if a solution can't be found,
            else returns None if the atom was successfully added.
        """
        return self.add_atoms([atom])

    def _add_atom(self, atom, stack, dbs):
        ret = self._rec_add_atom(atom, stack, dbs)
        if ret:
            self._dprint("failed- %s", ret)
            return ret, stack.events[-1]
        return ()

    def _stack_debugging_rec_add_atom(self, func, atom, stack, dbs, **kwds):
        current = len(stack)
        cycles = kwds.get('drop_cycles', False)
        reset_cycles = False
        if cycles and not self._debugging_drop_cycles:
            self._debugging_drop_cycles = reset_cycles = True
        if not reset_cycles:
            self._debugging_depth += 1

        assert current == self._debugging_depth -1
        ret = func(atom, stack, dbs, **kwds)
        assert current == len(stack)
        assert current == self._debugging_depth -1
        if not reset_cycles:
            self._debugging_depth -= 1
        else:
            self._debugging_drop_cycles = False
        return ret

    def _rec_add_atom(self, atom, stack, dbs, mode="none", drop_cycles=False):
        """Add an atom.

        :return: False on no issues (inserted succesfully),
            else a list of the stack that screwed it up.
        """
        assert hasattr(dbs, 'itermatch')
        limit_to_vdb = dbs == self.livefs_dbs

        matches = self._viable(stack, mode, atom, dbs, drop_cycles, limit_to_vdb)
        if matches is None:
            stack.pop_frame(False)
            return [atom]
        elif matches is True:
            stack.pop_frame(True)
            return None
        choices, matches = matches

        depth = stack.depth

        if stack:
            if limit_to_vdb:
                self._dprint(
                    "processing   %s%s  [%s]; mode %s vdb bound",
                    (depth*2*" ", atom, stack[-1].atom, mode))
            else:
                self._dprint(
                    "processing   %s%s  [%s]; mode %s",
                    (depth*2*" ", atom, stack[-1].atom, mode))
        else:
            self._dprint("processing   %s%s", (depth*2*" ", atom))

        ret = self.check_for_cycles(stack, stack.current_frame)
        if ret is not True:
            stack.pop_frame(ret is None)
            return ret

        failures = []

        debugging = self._debugging
        last_state = None
        while choices:
            if debugging:
                new_state = choices.state
                if last_state == new_state:
                    raise AssertionError(
                        "no state change detected, "
                        "old %r != new %r\nchoices(%r)\ncurrent(%r)\n"
                        "bdepend(%r)\ndepend(%r)\nrdepend(%r)\npdepend(%r)" % (
                            last_state, new_state, tuple(choices.matches), choices.current_pkg,
                            choices.bdepend, choices.depend, choices.rdepend, choices.pdepend,
                        )
                    )
                last_state = new_state
            additions = []

            self.notify_trying_choice(stack, atom, choices)

            if not choices.current_pkg.built or self.process_built_depends:
                new_additions, failures = self.process_dependencies_and_blocks(
                    stack, choices, 'depend', atom, depth)
                if failures:
                    continue
                additions += new_additions

                new_additions, failures = self.process_dependencies_and_blocks(
                    stack, choices, 'bdepend', atom, depth)
                if failures:
                    continue
                additions += new_additions

            new_additions, failures = self.process_dependencies_and_blocks(
                stack, choices, 'rdepend', atom, depth)
            if failures:
                continue
            additions += new_additions

            l = self.insert_choice(atom, stack, choices)
            if l is False:
                # this means somehow the node already slipped in.
                # so we exit now, we are satisfied
                self.notify_choice_succeeded(
                    stack, atom, choices,
                    "already exists in the state plan")
                stack.pop_frame(True)
                return None
            elif l is not None:
                # failure.
                self.notify_choice_failed(
                    stack, atom, choices,
                    "failed inserting: %s", l)
                self.state.backtrack(stack.current_frame.start_point)
                choices.force_next_pkg()
                continue

            new_additions, failures = self.process_dependencies_and_blocks(
                stack, choices, 'pdepend', atom, depth)
            if failures:
                continue
            additions += new_additions

            self.notify_choice_succeeded(stack, atom, choices)
            stack.pop_frame(True)
            return None

        self._dprint("no solution  %s%s", (depth*2*" ", atom))
        stack.add_event(("debug", "ran out of choices",))
        self.state.backtrack(stack.current_frame.start_point)
        # saving roll.  if we're allowed to drop cycles, try it again.
        # this needs to be *far* more fine grained also. it'll try
        # regardless of if it's a cycle issue
        if not drop_cycles and self.drop_cycles:
            stack.add_event(("cycle", stack.current_frame, "trying to drop any cycles"),)
            self._dprint(
                "trying saving throw for %s ignoring cycles",
                atom, "cycle")
            # note everything is retored to a pristine state prior also.
            stack[-1].ignored = True
            l = self._rec_add_atom(atom, stack, dbs,
                mode=mode, drop_cycles=True)
            if not l:
                stack.pop_frame(True)
                return None
        stack.pop_frame(False)
        return [atom] + failures

    def _viable(self, stack, mode, atom, dbs, drop_cycles, limit_to_vdb):
        """
        internal function to discern if an atom is viable, returning
        the choicepoint/matches iterator if viable.

        :param stack: current stack
        :type stack: :obj:`resolver_stack`
        :param mode: type of dependency (depend/rdepend)
        :type mode: str
        :param atom: atom for the current package
        :type atom: :obj:`pkgcore.ebuild.atom.atom`
        :param dbs: db list to walk
        :param drop_cycles: boolean controlling whether to drop dep cycles
        :param limit_to_vdb: boolean controlling considering pkgs only from the vdb
        :return: 3 possible; None (not viable), True (presolved),
          :obj:`caching_iter` (not solved, but viable), :obj:`choice_point`
        """
        choices = ret = None
        if atom in self.insoluble:
            ret = ((False, "globally insoluble"),{})
            matches = ()
        else:
            matches = self.state.match_atom(atom)
            if matches:
                ret = ((True,), {"pre_solved":True})
            else:
                # not in the plan thus far.
                matches = caching_iter(dbs.itermatch(atom))
                if matches:
                    choices = choice_point(atom, matches)
                    # ignore what dropped out, at this juncture we don't care.
                    choices.reduce_atoms(self.insoluble)
                    if not choices:
                        # and was intractable because it has a hard dep on an
                        # unsolvable atom.
                        ret = ((False, "pruning of insoluble deps "
                            "left no choices"), {})
                else:
                    ret = ((False, "no matches"), {})

        if choices is None:
            choices = choice_point(atom, matches)

        stack.add_frame(mode, atom, choices, dbs,
            self.state.current_state, drop_cycles, vdb_limited=limit_to_vdb)

        if not limit_to_vdb and not matches:
            self.insoluble.add(atom)
        if ret is not None:
            self.notify_viable(stack, atom, *ret[0], **ret[1])
            if ret[0][0] == True:
                state.add_backref_op(choices, choices.current_pkg).apply(self.state)
                return True
            return None
        return choices, matches

    def check_for_cycles(self, stack, cur_frame):
        """Check the current stack for cyclical issues.

        :param stack: current stack, a :obj:`resolver_stack` instance
        :param cur_frame: current frame, a :obj:`resolver_frame` instance
        :return: True if no issues and resolution should continue, else the
            value to return after collapsing the calling frame
        """
        force_vdb = False
        for frame in stack.slot_cycles(cur_frame, reverse=True):
            if not any(f.mode == 'pdepend' for f in
                islice(stack, stack.index(frame), stack.index(cur_frame))):
                # exact same pkg.
                if frame.mode in ('bdepend', 'depend'):
                    # ok, we *must* go vdb if not already.
                    if frame.current_pkg.repo.livefs:
                        if cur_frame.current_pkg.repo.livefs:
                            return None
                        # force it to vdb.
                    if cur_frame.current_pkg.repo.livefs:
                        return True
                    elif cur_frame.current_pkg == frame.current_pkg and \
                        cur_frame.mode == 'pdepend':
                        # if non vdb and it's a post_rdeps cycle for the cur
                        # node, exempt it; assuming the stack succeeds,
                        # it's satisfied
                        return True
                    force_vdb = True
                    break
                else:
                    # should be doing a full walk of the cycle here, seeing
                    # if an rdep becomes a dep.
                    return None
                # portage::gentoo -> rysnc -> portage::vdb; let it process it.
                return True
            # only need to look at the most recent match; reasoning is simple,
            # logic above forces it to vdb if needed.
            break
        if not force_vdb:
            return True
        # we already know the current pkg isn't livefs; force livefs to
        # sidestep this.
        cur_frame.parent.events.append(("cycle", cur_frame, "limiting to vdb"))
        cur_frame.ignored = True
        return self._rec_add_atom(cur_frame.atom, stack,
            self.livefs_dbs, mode=cur_frame.mode,
            drop_cycles = cur_frame.drop_cycles)

    def process_dependencies_and_blocks(self, stack, choices, attr,
                                        atom=None, depth=None):
        if atom is None:
            atom = stack.current_frame.atom
        if depth is None:
            depth = stack.depth
        depset = self.depset_reorder(getattr(choices, attr), attr)
        l = self.process_dependencies(stack, choices, attr, depset, atom)
        if len(l) == 1:
            self._dprint(
                "resetting for %s%s because of %s: %s",
                (depth*2*" ", atom, attr, l[0]))
            self.state.backtrack(stack.current_frame.start_point)
            return [], l[0]

        additions = l[0]
        return additions, []

    def process_dependencies(self, stack, choices, mode, depset, atom):
        failure = []
        additions, blocks, = [], []
        cur_frame = stack.current_frame
        self.notify_starting_mode(mode, stack)
        for potentials in depset:
            failure = []
            for or_node in potentials:
                if or_node.blocks:
                    failure = self.process_blocker(stack, choices, or_node, mode, atom)
                    if not failure:
                        blocks.append(or_node)
                        break
                else:
                    failure = self._rec_add_atom(or_node, stack,
                        cur_frame.dbs, mode=mode,
                        drop_cycles=cur_frame.drop_cycles)
                    if not failure:
                        additions.append(or_node)
                        break
                    # XXX this is whacky tacky fantastically crappy
                    # XXX kill it; purpose seems... questionable.
                    if cur_frame.drop_cycles:
                        self._dprint(
                            "%s level cycle: %s: "
                            "dropping cycle for %s from %s",
                            (mode, cur_frame.atom, or_node, cur_frame.current_pkg),
                            "cycle")
                        failure = None
                        break

                if cur_frame.reduce_solutions(or_node):
                    # pkg changed.
                    return [failure]
                continue
            else: # didn't find any solutions to this or block.
                cur_frame.reduce_solutions(potentials)
                return [potentials]
        else: # all potentials were usable.
            return additions, blocks

    def process_blocker(self, stack, choices, blocker, mode, atom):
        ret = self.insert_blockers(stack, choices, [blocker])
        if ret is None:
            return []
        self.notify_choice_failed(
            stack, atom, choices,
            "%s blocker: %s conflicts w/ %s", (mode, ret[0], ret[1]))
        return [ret[0]]

    def _ensure_livefs_is_loaded_preloaded(self, restrict):
        return

    def _ensure_livefs_is_loaded_nonpreloaded(self, restrict):
        # do a trick to make the resolver now aware of vdb pkgs if needed
        # check for any matches; none, try and insert vdb nodes.
        l = self.state.match_atom(restrict)
        if not l:
            # hmm. ok... no conflicts, so we insert in vdb matches
            # to trigger a replace instead of an install
            for pkg in self.livefs_dbs.itermatch(restrict):
                self._dprint("inserting vdb node for %s %s", (restrict, pkg))
                c = choice_point(restrict, [pkg])
                state.add_op(c, c.current_pkg, force=True).apply(self.state)

    def insert_choice(self, atom, stack, choices):
        # first, check for conflicts.
        # lil bit fugly, but works for the moment
        if not choices.current_pkg.repo.livefs:
            self._ensure_livefs_is_loaded(choices.current_pkg.slotted_atom)
        conflicts = state.add_op(choices, choices.current_pkg).apply(self.state)
        if conflicts:
            # this means in this branch of resolution, someone slipped
            # something in already. cycle, basically.
            # hack.  see if what was inserted is enough for us.

            # this is tricky... if it's the same node inserted
            # (cycle), then we ignore it; this does *not* perfectly
            # behave though, doesn't discern between repos.

            # Note that virtual pkg conflicts are skipped since it's assumed
            # they are injected.
            virtual = (any(not getattr(x, 'package_is_real', True) for x in conflicts)
                       or not choices.current_pkg.package_is_real)
            if (virtual or (len(conflicts) == 1 and conflicts[0] == choices.current_pkg and
                    (conflicts[0].repo.livefs == choices.current_pkg.repo.livefs and
                    atom.match(conflicts[0])))):
                # early exit. means that a cycle came about, but exact
                # same result slipped through.
                return False

            self._dprint(
                "was trying to insert atom '%s' pkg '%s',\nbut '[%s]' exists already",
                (atom, choices.current_pkg, ", ".join(map(str, conflicts))))

            try_rematch = False
            if any(True for x in conflicts if isinstance(x, restriction.base)):
                # blocker was caught
                try_rematch = True
            elif not any(True for x in conflicts if not self.vdb_restrict.match(x)):
                # vdb entry, replace.
                if self.vdb_restrict.match(choices.current_pkg):
                    # we're replacing a vdb entry with a vdb entry?  wtf.
                    print("internal weirdness spotted- vdb restrict matches, "
                          "but current doesn't, bailing")
                    raise Exception("internal weirdness- vdb restrict matches ",
                                    "but current doesn't. bailing- run w/ --debug")
                conflicts = state.replace_op(choices, choices.current_pkg).apply(self.state)
                if not conflicts:
                    self._dprint(
                        "replacing vdb entry for '%s' with pkg '%s'",
                        (atom, choices.current_pkg))

            else:
                try_rematch = True
            if try_rematch:
                # XXX: this block looks whacked.  figure out what it's up to.
                l2 = self.state.match_atom(atom)
                if l2 == [choices.current_pkg]:
                    # stop resolution.
                    conflicts = False
                elif l2:
                    # potentially need to do some form of cleanup here.
                    conflicts = False
        else:
            conflicts = None
        return conflicts

    def generate_mangled_blocker(self, choices, blocker):
        """converts a blocker into a "cannot block ourself" block"""
        # note the second Or clause is a bit loose; allows any version to
        # slip through instead of blocking everything that isn't the
        # parent pkg
        if blocker.category != 'virtual':
            return blocker
        return packages.AndRestriction(blocker,
            packages.PackageRestriction("provider.key",
                values.StrExactMatch(choices.current_pkg.key),
                negate=True, ignore_missing=True))

    def insert_blockers(self, stack, choices, blocks):
        # level blockers.
        was_livefs = choices.current_pkg.repo.livefs
        for x in blocks:
            if not was_livefs:
                self._ensure_livefs_is_loaded(x)

            rewrote_blocker = self.generate_mangled_blocker(choices, x)
            l = self.state.add_blocker(choices, rewrote_blocker, key=x.key)
            if l:
                # blocker caught something. yay.
                self._dprint(
                    "%s blocker %s hit %s for atom %s pkg %s",
                    (stack[-1].mode, x, l, stack[-1].atom, choices.current_pkg))
                if x.weak_blocker:
                    # note that we use the top frame of the stacks' dbs; this
                    # is to allow us to upgrade as needed.
                    # For this to match, it's *only* possible if the blocker is resolved
                    # since the limiter is already in place.
                    result = self._rec_add_atom(packages.KeyedAndRestriction(
                        restriction.Negate(x), _atom.atom(x.key), key=x.key), stack, stack[0].dbs)
                    if not result:
                        # ok, inserted a new version.  did it take care of the conflict?
                        # it /may/ not have, via filling a different slot...
                        result = self.state.match_atom(x)
                        if not result:
                            # ignore the blocker, we resolved past it.
                            continue
                return x, l
        return None

    def free_caches(self):
        for repo in self.all_raw_dbs:
            repo.clear()

    # selection strategies for atom matches

    def default_depset_reorder_strategy(self, depset, mode):
        for or_block in depset:
            vdb = []
            non_vdb = []
            if len(or_block) == 1:
                yield or_block
                continue
            for atom in or_block:
                if atom.blocks:
                    non_vdb.append(atom)
                elif self.state.match_atom(atom):
                    vdb.append(atom)
                elif atom in self.livefs_dbs:
                    vdb.append(atom)
                else:
                    non_vdb.append(atom)
            if vdb:
                yield vdb + non_vdb
            else:
                yield or_block

    @staticmethod
    def default_global_strategy(dbs, atom):
        return chain(*[repo.itermatch(atom) for repo in dbs])

    @staticmethod
    def just_livefs_dbs(dbs):
        return (r for r in dbs if r.livefs)

    @staticmethod
    def just_nonlivefs_dbs(dbs):
        return (r for r in dbs if not r.livefs)

    @classmethod
    def prefer_livefs_dbs(cls, dbs, just_vdb=None):
        """
        :param dbs: db list to walk
        :param just_vdb: if None, no filtering; if True, just vdb, if False,
          non-vdb only
        :return: yields repos in requested ordering
        """
        return chain(cls.just_livefs_dbs(dbs), cls.just_nonlivefs_dbs(dbs))

    @classmethod
    def prefer_nonlivefs_dbs(cls, dbs, just_vdb=None):
        """
        :param dbs: db list to walk
        :param just_vdb: if None, no filtering; if True, just vdb, if False,
          non-vdb only
        :return: yields repos in requested ordering
        """
        return chain(cls.just_nonlivefs_dbs(dbs), cls.just_livefs_dbs(dbs))

    @classmethod
    def prefer_highest_version_strategy(cls, dbs):
        return misc.multiplex_sorting_repo(
            highest_iter_sort, cls.prefer_livefs_dbs(dbs))

    @staticmethod
    def prefer_lowest_version_strategy(dbs):
        return misc.multiplex_sorting_repo(lowest_iter_sort, dbs)

    @classmethod
    def prefer_downgrade_version_strategy(cls, restrict, dbs):
        return misc.multiplex_sorting_repo(
            partial(downgrade_iter_sort, restrict),
            cls.prefer_nonlivefs_dbs(dbs))

    @classmethod
    def prefer_reuse_strategy(cls, dbs):
        return multiplex.tree(
            misc.multiplex_sorting_repo(
                highest_iter_sort, cls.just_livefs_dbs(dbs)),
            misc.multiplex_sorting_repo(
                highest_iter_sort, cls.just_nonlivefs_dbs(dbs)),
        )
