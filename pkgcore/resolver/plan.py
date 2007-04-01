# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

import operator
from itertools import chain, islice
from collections import deque

from pkgcore.resolver.choice_point import choice_point
from pkgcore.restrictions import packages, values, restriction
from pkgcore.repository.misc import caching_repo
from pkgcore.resolver import state

from snakeoil.currying import partial, post_curry
from snakeoil.compatibility import any
from snakeoil.iterables import caching_iter, iter_sort


limiters = set(["cycle"]) # [None])
def dprint(fmt, args=None, label=None):
    if limiters is None or label in limiters:
        if args is None:
            print fmt
        else:
            print fmt % args


#iter/pkg sorting functions for selection strategy
pkg_sort_highest = partial(sorted, reverse=True)
pkg_sort_lowest = sorted

pkg_grabber = operator.itemgetter(0)

def highest_iter_sort(l, pkg_grabber=pkg_grabber):
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
    l.sort(f, key=pkg_grabber, reverse=True)
    return l


def lowest_iter_sort(l, pkg_grabber=pkg_grabber):
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
    l.sort(f, key=pkg_grabber)
    return l


class resolver_frame(object):

    __slots__ = ("atom", "choices", "mode", "start_point", "dbs",
        "depth", "drop_cycles", "__weakref__")

    def __init__(self, mode, atom, choices, dbs, start_point, depth,
        drop_cycles):
        self.atom = atom
        self.choices = choices
        self.dbs = dbs
        self.mode = mode
        self.start_point = start_point
        self.depth = depth
        self.drop_cycles = drop_cycles

    def __str__(self):
        return "frame: mode %r: atom %s: current %s" % \
            (self.mode, self.atom, self.current_pkg)

    @property
    def current_pkg(self):
        try:
            return self.choices.current_pkg
        except IndexError:
            return None


class resolver_stack(deque):

    frame_klass = resolver_frame
    depth = property(len)
    current_frame = property(operator.itemgetter(-1))

    def __str__(self):
        return 'resolver stack:\n  %s' % '\n  '.join(str(x) for x in self)

    def __repr__(self):
        return '<%s: %r>' % (self.__class__.__name__,
            tuple(repr(x) for x in self))

    def add_frame(self, mode, atom, choices, dbs, start_point, drop_cycles):
        frame = self.frame_klass(mode, atom, choices, dbs, start_point,
            self.depth + 1, drop_cycles)
        self.append(frame)
        return frame

    def pop_frame(self):
        self.pop()

    def is_cycle(self, atom, cur_choice, attr, start=0):
        # short cut...
        if attr == "post_rdepends":
            # not possible for a cycle we'll care about to exist.
            # the 'cut off' point is for the new atom, thus not possible for
            # a cycle.
            return -1

        cycle_start = -1
        if start != 0:
            i = islice(self, start, None)
        else:
            i = self
        for idx, x in enumerate(i):
            if x.mode == "post_rdepends":
                cycle_start = -1
            if x.atom == atom:
                cycle_start = idx

        if cycle_start != -1:
            # deque can't be sliced, thus islice
            if attr is not None:
                s = ', '.join('[%s: %s]' % (x.atom, x.current_pkg) for x in
                    islice(self, cycle_start))
                if s:
                    s += ', '
                s += '[%s: %s]' % (atom, cur_choice.current_pkg)
                dprint("%s level cycle: stack: %s\n",
                    (attr, s), "cycle")
            return cycle_start + start
        return -1


class merge_plan(object):

    vdb_restrict = packages.PackageRestriction("repo.livefs",
        values.EqualityMatch(True))

    def __init__(self, dbs, per_repo_strategy,
                 global_strategy=None,
                 depset_reorder_strategy=None,
                 process_built_depends=False,
                 drop_cycles=False):

        if not isinstance(dbs, (list, tuple)):
            dbs = [dbs]

        if global_strategy is None:
            global_strategy = self.default_global_strategy

        if depset_reorder_strategy is None:
            depset_reorder_strategy = self.default_depset_reorder_strategy

        self.depset_reorder = depset_reorder_strategy
        self.per_repo_strategy = per_repo_strategy
        self.global_strategy = global_strategy
        self.forced_atoms = set()
        self.all_dbs = [caching_repo(x, self.per_repo_strategy) for x in dbs]
        self.livefs_dbs = [x for x in self.all_dbs if x.livefs]
        self.dbs = [x for x in self.all_dbs if not x.livefs]
        self.state = state.plan_state()
        self.insoluble = set()
        self.vdb_preloaded = False
        self.drop_cycles = drop_cycles
        self.process_built_depends = process_built_depends

    def notify_starting_mode(self, mode, stack):
        if mode == "post_rdepends":
            mode = 'prdepends'
        dprint("%s:%s%s: started: %s" % 
            (mode, ' ' * ((stack.current_frame.depth * 2) + 12 - len(mode)),
                stack.current_frame.atom,
                stack.current_frame.choices.current_pkg)
            )

    def notify_trying_choice(self, stack, atom, choices):
        dprint("choose for %s%s, %s",
               (stack.depth *2*" ", atom, choices.current_pkg))

    def notify_choice_failed(self, stack, atom, choices, msg, msg_args=()):
        if msg:
            msg = ' %s' % (msg % msg_args)
        dprint("choice for %s%s, %s failed: %s", 
            (stack.depth * 2 * ' ', atom, choices.current_pkg, msg))

    def load_vdb_state(self):
        for r in self.livefs_dbs:
            for pkg in r.__db__:
                dprint("inserting %s from %s", (pkg, r), "vdb")
                ret = self.add_atom(pkg.versioned_atom, dbs=self.livefs_dbs)
                dprint("insertion of %s from %s: %s", (pkg, r, ret), "vdb")
                if ret != []:
                    raise Exception(
                        "couldn't load vdb state, %s %s" %
                        (pkg.versioned_atom, ret))
        self.vdb_preloaded = True

    def add_atom(self, atom, dbs=None):
        """add an atom, recalculating as necessary.

        @return: the last unresolvable atom stack if a solution can't be found,
            else returns [] (meaning the atom was successfully added).
        """
        if dbs is None:
            dbs = self.all_dbs
        if atom not in self.forced_atoms:
            stack = resolver_stack()
            ret = self._rec_add_atom(atom, stack, dbs)
            if ret:
                dprint("failed- %s", ret)
                return ret
            else:
                self.forced_atoms.add(atom)

        return []

    def process_depends(self, stack, depset):
        failure = []
        additions, blocks, = [], []
        cur_frame = stack.current_frame
        self.notify_starting_mode("depends", stack)
        for datom_potentials in depset:
            failure = []
            for datom in datom_potentials:
                if datom.blocks:
                    # don't register, just do a scan. and this sucks
                    # because any later insertions prior to this won't
                    # get hit by the blocker
                    l = self.state.match_atom(datom)
                    if l:
#                        dprint("depends blocker messing with us- "
#                            "skipping "
#                            "atom %s, pkg %s, ret %s",
#                            (cur_frame.atom, cur_frame.choices.current_pkg, l),
#                            "blockers")
                        continue
                else:
                    index = stack.is_cycle(datom, cur_frame.choices,
                        "depends")
                    looped = ignore = False
                    stack_end = len(stack) - 1
                    # this logic is admittedly semi tricky.
                    while index != -1:
                        looped = True
                        # see if it's a vdb node already; if it's a cycle between
                        # the same vdb node, ignore it (ignore self-dependant
                        # depends level installed deps for the same node iow)
                        if ((index < stack_end and index) and
                            (stack[index - 1].current_pkg ==
                            cur_frame.current_pkg)
                            and cur_frame.current_pkg.repo.livefs):
                            # we're in a cycle of depends level vdb nodes;
                            # they cyclical pkg is installed already, thus
                            # its satisfied itself.
                            dprint("depends:     %snonissue: vdb bound cycle "
                                "for %s via %s, exempting" %
                                (cur_frame.depth *2 * " ", cur_frame.atom,
                                cur_frame.choices.current_pkg))
                            ignore = True
                            break
                        else:
                            # ok, so the first candidate wasn't vdb.
                            # see if there are more.
                            index = stack.is_cycle(datom,
                                cur_frame.choices, None, start=index + 1)
                    else:
                        # ok.  it exited on its own.  meaning either no cycles,
                        # or no vdb exemptions where found.
                        if looped:
                            # non vdb level cycle.  vdb bound?
                            # this sucks also- any code that reorders the db
                            # on the fly to not match livefs_dbs is going to
                            # have issues here.
                            if self.livefs_dbs == cur_frame.dbs:
                                dprint("depends:     %snon-vdb cycle that "
                                    "went vdb for %s via %s, failing" %
                                    (cur_frame.depth *2 * " ", cur_frame.atom,
                                    cur_frame.choices.current_pkg))
                                failure = [datom]
                                continue
                            # try forcing vdb level match.
                            dbs = self.livefs_dbs
                        else:
                            # use normal db, no cycles.
                            dbs = cur_frame.dbs
                    if ignore:
                        # vdb contained cycle; ignore it.
                        break
                    failure = self._rec_add_atom(datom, stack,
                        dbs, mode="depends",
                        drop_cycles=cur_frame.drop_cycles)
                    if failure and cur_frame.drop_cycles:
                        dprint("depends level cycle: %s: "
                               "dropping cycle for %s from %s",
                                (cur_frame.atom, datom,
                                 cur_frame.current_pkg),
                                "cycle")
                        failure = []
                        # note we trigger a break ourselves.
                        break

                    if failure:
                        dprint("depends:     %s%s: reducing %s from %s",
                               (cur_frame.depth *2 * " ", cur_frame.atom,
                                datom,
                                cur_frame.choices.current_pkg))
                        if cur_frame.choices.reduce_atoms(datom):
                            # this means the pkg just changed under our feet.
                            return [[datom] + failure]
                        continue
                additions.append(datom)
                break
            else: # didn't find any solutions to this or block.
                cur_frame.choices.reduce_atoms(datom_potentials)
                return [datom_potentials]
        else: # all potentials were usable.
            return additions, blocks

    def process_rdepends(self, stack, attr, depset):
        failure = []
        additions, blocks, = [], []
        cur_frame = stack.current_frame
        self.notify_starting_mode(attr, stack)
        for ratom_potentials in depset:
            failure = []
            for ratom in ratom_potentials:
                if ratom.blocks:
                    blocks.append(ratom)
                    break
                index = stack.is_cycle(ratom, cur_frame.choices, attr)
                if index != -1:
                    # cycle.  whee.
                    if cur_frame.dbs is self.livefs_dbs:
                        # well. we know the node is valid, so we can
                        # ignore this cycle.
                        failure = []
                    else:
                        # XXX this is faulty for rdepends/prdepends most likely

                        if stack[index].mode == attr:
                            # contained rdepends cycle... ignore it.
                            failure = []
                        else:
                            # force limit_to_vdb to True to try and
                            # isolate the cycle to installed vdb
                            # components
                            failure = self._rec_add_atom(ratom, stack,
                                self.livefs_dbs, mode=attr,
                                drop_cycles=cur_frame.drop_cycles)
                            if failure and cur_frame.drop_cycles:
                                dprint("rdepends level cycle: %s: "
                                       "dropping cycle for %s from %s",
                                       (atom, ratom, cur_frame.current_pkg),
                                       "cycle")
                                failure = []
                                break
                else:
                    failure = self._rec_add_atom(ratom, stack,
                        cur_frame.dbs, mode=attr,
                        drop_cycles=cur_frame.drop_cycles)
                if failure:
                    # reduce.
                    if cur_frame.choices.reduce_atoms(ratom):
                        # pkg changed.
                        return [[ratom] + failure]
                    continue
                additions.append(ratom)
                break
            else: # didn't find any solutions to this or block.
                cur_frame.choices.reduce_atoms(ratom_potentials)
                return [ratom_potentials]
        else: # all potentials were usable.
            return additions, blocks

    def insert_choice(self, atom, stack, choices):
        # well, we got ourselvs a resolution.
        # do a trick to make the resolver now aware of vdb pkgs if needed
        if not self.vdb_preloaded and not choices.current_pkg.repo.livefs:
            slotted_atom = choices.current_pkg.slotted_atom
            l = self.state.match_atom(slotted_atom)
            if not l:
                # hmm. ok... no conflicts, so we insert in vdb matches
                # to trigger a replace instead of an install
                for repo in self.livefs_dbs:
                    m = repo.match(slotted_atom)
                    if m:
                        c = choice_point(slotted_atom, m)
                        state.add_op(c, c.current_pkg, force=True).apply(self.state)
                        break

        # first, check for conflicts.
        # lil bit fugly, but works for the moment
        conflicts = state.add_op(choices, choices.current_pkg).apply(self.state)
        if conflicts:
            # this means in this branch of resolution, someone slipped
            # something in already. cycle, basically.
            dprint("was trying to insert atom '%s' pkg '%s',\n"
                   "but '[%s]' exists already",
                   (atom, choices.current_pkg,
                   ", ".join(map(str, conflicts))))
            # hack.  see if what was insert is enough for us.

            # this is tricky... if it's the same node inserted
            # (cycle), then we ignore it; this does *not* perfectly
            # behave though, doesn't discern between repos.

            if (len(conflicts) == 1 and conflicts[0] == choices.current_pkg and
                conflicts[0].repo.livefs == choices.current_pkg.repo.livefs and
                atom.match(conflicts[0])):

                # early exit. means that a cycle came about, but exact
                # same result slipped through.
                dprint("non issue, cycle for %s pkg %s resolved to same pkg" %
                       (repr(atom), choices.current_pkg))
                return False
            try_rematch = False
            if any(True for x in conflicts if isinstance(x, restriction.base)):
                # blocker was caught
                try_rematch = True
            elif not any (True for x in conflicts if not
                self.vdb_restrict.match(x)):
                # vdb entry, replace.
                if self.vdb_restrict.match(choices.current_pkg):
                    # we're replacing a vdb entry with a vdb entry?  wtf.
                    print ("internal weirdness spotted- vdb restrict matches, "
                        "but current doesn't, bailing")
                    raise Exception()
                conflicts = state.replace_op(choices, choices.current_pkg).apply(
                    self.state)
            else:
                try_rematch = True
            if try_rematch:
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

    def _viable(self, atom, stack, dbs, limit_to_vdb):
        """
        internal function to discern if an atom is viable, returning
        the matches iter if so

        @return: 3 possible; None (not viable), True (presolved),
          L{caching_iter} (not solved, but viable)
        """
        if atom in self.insoluble:
            dprint("processing   %s%s: marked insoluble already",
                   (stack.depth *2 * " ", atom))
            return None
        l = self.state.match_atom(atom)
        if l:
            if stack:
                dprint("pre-solved  %s%s, [%s] [%s]",
                       (((stack.depth*2) + 1)*" ", atom, stack[-1].atom,
                        ", ".join(str(x) for x in l)), 'pre-solved')
            else:
                dprint("pre-solved %s%s, [%s]",
                       (stack.depth*2*" ", atom, ", ".join(str(x) for x in l)),
                       'pre-solved')
            return True
        # not in the plan thus far.
        matches = caching_iter(self.global_strategy(self, dbs, atom))
        if matches:
            choices = choice_point(atom, matches)
            # ignore what dropped out, at this juncture we don't care.
            choices.reduce_atoms(self.insoluble)
            if not choices:
                s = 'first level'
                if stack:
                    s = stack[-1].atom
                dprint("filtering    %s%s  [%s] reduced it to no matches",
                       (stack.depth * 2 * " ", atom, s))
                matches = None
                # and was intractable because it has a hard dep on an
                # unsolvable atom.
        if not matches:
            if not limit_to_vdb:
                self.insoluble.add(atom)
            s = 'first level'
            if stack:
                s = stack[-1].atom
            dprint("processing   %s%s  [%s] no matches",
                   (stack.depth *2 * " ", atom, s))
            return None
        return choices, matches

    def _rec_add_atom(self, atom, stack, dbs, mode="none",
        drop_cycles=False):
        """Add an atom.

        @return: False on no issues (inserted succesfully),
            else a list of the stack that screwed it up.
        """
        limit_to_vdb = dbs == self.livefs_dbs

        depth = stack.depth

        matches = self._viable(atom, stack, dbs, limit_to_vdb)
        if matches is None:
            return [atom]
        elif matches is True:
            return None
        choices, matches = matches

        # experiment. ;)
        # see if we can insert or not at this point (if we can't, no
        # point in descending)

        if stack:
            if limit_to_vdb:
                dprint("processing   %s%s  [%s]; mode %s vdb bound",
                       (depth *2 * " ", atom, stack[-1].atom, mode))
            else:
                dprint("processing   %s%s  [%s]; mode %s",
                       (depth *2 * " ", atom, stack[-1].atom, mode))
        else:
            dprint("processing   %s%s", (depth *2 * " ", atom))

        stack.add_frame(mode, atom, choices, dbs,
            self.state.current_state, drop_cycles)

        blocks = []
        failures = []

        last_state = None
        while choices:
            new_state = choices.state
            if last_state == new_state:
                raise AssertionError("no state change detected, "
                    "old %r != new %r\nchoices(%r)\ncurrent(%r)\ndepends(%r)\n"
                    "rdepends(%r)\npost_rdepends(%r)\nprovides(%r)" %
                    (last_state, new_state, tuple(choices.matches),
                        choices.current_pkg, choices.depends,
                        choices.rdepends, choices.post_rdepends,
                        choices.provides))
            last_state = new_state
            additions, blocks = [], []

            self.notify_trying_choice(stack, atom, choices)

            if not choices.current_pkg.built or self.process_built_depends:
                l = self.process_depends(stack,
                    self.depset_reorder(self, choices.depends, "depends"))
                if len(l) == 1:
                    dprint("reseting for %s%s because of depends: %s",
                           (depth*2*" ", atom, l[0][-1]))
                    self.state.backtrack(stack.current_frame.start_point)
                    failures = l[0]
                    continue
                additions += l[0]
                blocks += l[1]

            l = self.process_rdepends(stack, "rdepends",
                self.depset_reorder(self, choices.rdepends, "rdepends"))
            if len(l) == 1:
                dprint("reseting for %s%s because of rdepends: %s",
                       (depth*2*" ", atom, l[0]))
                self.state.backtrack(stack.current_frame.start_point)
                failures = l[0]
                continue
            additions += l[0]
            blocks += l[1]

            l = self.insert_choice(atom, stack, choices)
            if l is False:
                # this means somehow the node already slipped in.
                # so we exit now, we are satisfied
                self.notify_choice_failed(stack, atom, choices,
                    "already exists in the state plan")
                stack.pop_frame()
                return None
            elif l is not None:
                # failure.
                self.notify_failed_choice(stack, atom, choices,
                    "failed inserting: %s", l)
                self.state.backtrack(stack.current_frame.start_point)
                choices.force_next_pkg()
                continue

            fail = True
            for x in choices.provides:
                l = state.add_op(choices, x).apply(self.state)
                if l and l != [x]:
                    if len(stack) > 1:
                        if not stack[-2].atom.match(x):
                            print "provider conflicted... how?"
                            fail = [x]
                            break
            else:
                fail = False
            if fail:
                self.state.backtrack(stack.current_frame.start_point)
                choices.force_next_pkg()
                continue

            # level blockers.
            fail = True
            for x in blocks:

                # check for any matches; none, try and insert vdb nodes.
                if not self.vdb_preloaded and \
                    not choices.current_pkg.repo.livefs and \
                    not self.state.match_atom(x):
                    for repo in self.livefs_dbs:
                        m = repo.match(x)
                        if m:
                            dprint("inserting vdb node for blocker"
                                " %s %s" % (x, m[0]))
                            # ignore blockers for for vdb atm, since
                            # when we level this nodes blockers they'll
                            # hit
                            c = choice_point(x, m)
                            state.add_op(c, c.current_pkg, force=True).apply(
                                self.state)
                            break

                rewrote_blocker = self.generate_mangled_blocker(choices, x)
                l = self.state.add_blocker(choices, rewrote_blocker, key=x.key)
                if l:
                    # blocker caught something. yay.
                    dprint("rdepend blocker %s hit %s for atom %s pkg %s",
                           (x, l, atom, choices.current_pkg))
                    failures = [x]
                    break
            else:
                fail = False
            if fail:
                self.notify_choice_failed(stack, atom, choices,
                    "failed due to %s", x)
                choices.reduce_atoms(x)
                self.state.backtrack(stack.current_frame.start_point)
                continue

            # reset blocks for pdepend proccesing
            blocks = []
            l = self.process_rdepends(stack, "post_rdepends",
                self.depset_reorder(self, choices.post_rdepends,
                                    "post_rdepends"))

            if len(l) == 1:
                dprint("reseting for %s%s because of rdepends: %s",
                       (depth*2*" ", atom, l[0]))
                self.state.backtrack(stack.current_frame.start_point)
                failures = l[0]
                continue
            additions += l[0]
            blocks += l[1]

            # level blockers.
            fail = True
            for x in blocks:
                # hackity hack potential- say we did this-
                # disallowing blockers from blocking what introduced them.
                # iow, we can't block ourselves (can block other
                # versions, but not our exact self)
                # this might be suspect mind you...
                # disabled, but something to think about.

                l = self.state.add_blocker(choices,
                    self.generate_mangled_blocker(choices, x), key=x.key)
                if l:
                    # blocker caught something. yay.
                    self.notify_failed_choice(stack, atom, choices,
                        "rdepend blocker %s hit %s", (x, l))
                    failures = [x]
                    break
            else:
                fail = False
            if fail:
                self.state.backtrack(stack.current_frame.start_point)
                choices.force_next_pkg()
                continue
            break

        else:
            dprint("no solution  %s%s", (depth*2*" ", atom))
            stack.pop_frame()
            self.state.backtrack(stack.current_frame.start_point)
            # saving roll.  if we're allowed to drop cycles, try it again.
            # this needs to be *far* more fine grained also. it'll try
            # regardless of if it's cycle issue
            if not drop_cycles and self.drop_cycles:
                dprint("trying saving throw for %s ignoring cycles",
                       atom, "cycle")
                # note everything is retored to a pristine state prior also.
                l = self._rec_add_atom(atom, stack, dbs,
                    mode=mode, drop_cycles=True)
                if not l:
                    return None
            return [atom] + failures

        stack.pop_frame()
        return None

    def generate_mangled_blocker(self, choices, blocker):
        """converts a blocker into a "cannot block ourself" block"""
        # note the second Or clause is a bit loose; allows any version to
        # slip through instead of blocking everything that isn't the
        # parent pkg
        new_atom = packages.AndRestriction(
            packages.OrRestriction(packages.PackageRestriction(
                "actual_pkg",
                restriction.FakeType(choices.current_pkg.versioned_atom,
                                     values.value_type),
                ignore_missing=True),
            choices.current_pkg.versioned_atom, negate=True),
            blocker, finalize=True)
        return new_atom

    def free_caches(self):
        for repo in self.all_dbs:
            repo.clear()

    # selection strategies for atom matches

    @staticmethod
    def default_depset_reorder_strategy(self, depset, mode):
        for or_block in depset:
            vdb = []
            non_vdb = []
            if len(or_block) == 1:
                yield or_block
                continue
            for atom in or_block:
                if atom.blocks:
                    nonvdb.append(atom)
                elif self.state.match_atom(atom):
                    vdb.append(atom)
                elif caching_iter(p for r in self.livefs_dbs
                    for p in r.match(atom)):
                    vdb.append(atom)
                else:
                    non_vdb.append(atom)
            if vdb:
                yield vdb + non_vdb
            else:
                yield or_block

    @staticmethod
    def default_global_strategy(self, dbs, atom):
        return chain(*[repo.match(atom) for repo in dbs])

    @staticmethod
    def just_livefs_dbs(dbs):
        for r in dbs:
            if r.livefs:
                yield r

    @staticmethod
    def just_nonlivefs_dbs(dbs):
        for r in dbs:
            if not r.livefs:
                yield r

    @classmethod
    def prefer_livefs_dbs(cls, dbs, just_vdb=None):
        """
        @param dbs: db list to walk
        @param just_vdb: if None, no filtering; if True, just vdb, if False,
          non-vdb only
        @return: yields repositories in requested ordering
        """
        return chain(cls.just_livefs_dbs(dbs), cls.just_nonlivefs_dbs(dbs))

    @staticmethod
    def prefer_highest_version_strategy(self, dbs, atom):
        # XXX rework caching_iter so that it iter's properly
        return iter_sort(highest_iter_sort,
                         *[repo.match(atom)
                         for repo in self.prefer_livefs_dbs(dbs)])

    @staticmethod
    def prefer_lowest_version_strategy(self, dbs, atom):
        return iter_sort(lowest_iter_sort,
                         self.default_global_strategy(self, dbs, atom))

    @staticmethod
    def prefer_reuse_strategy(self, dbs, atom):

        return chain(
            iter_sort(highest_iter_sort,
                *[repo.match(atom) for repo in self.just_livefs_dbs(dbs)]),
            iter_sort(highest_iter_sort,
                *[repo.match(atom) for repo in self.just_nonlivefs_dbs(dbs)])
        )

    def generic_force_version_strategy(self, vdb, dbs, atom, iter_sorter,
                                       pkg_sorter):
        try:
            # nasty, but works.
            yield iter_sort(iter_sorter,
                            *[r.itermatch(atom, sorter=pkg_sorter)
                              for r in [vdb] + dbs]).next()
        except StopIteration:
            # twas no matches
            pass

    force_max_version_strategy = staticmethod(
        post_curry(generic_force_version_strategy,
                   highest_iter_sort, pkg_sort_highest))
    force_min_version_strategy = staticmethod(
        post_curry(generic_force_version_strategy,
                   lowest_iter_sort, pkg_sort_lowest))
