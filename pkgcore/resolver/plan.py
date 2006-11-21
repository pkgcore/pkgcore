# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

import operator
from itertools import chain, islice
from collections import deque
from pkgcore.util.compatibility import any
from pkgcore.util.iterables import caching_iter, iter_sort
from pkgcore.util.mappings import OrderedDict
from pkgcore.resolver.pigeonholes import PigeonHoledSlots
from pkgcore.resolver.choice_point import choice_point
from pkgcore.util.currying import partial, post_curry
from pkgcore.restrictions import packages, values, restriction
from pkgcore.package.mutated import MutatedPkg
from pkgcore.util.klass import GetAttrProxy


limiters = set(["cycle"]) # [None])
def dprint(fmt, args=None, label=None):
    if limiters is None or label in limiters:
        if args is None:
            print fmt
        else:
            print fmt % args

def index_gen(iterable):
    """returns zero for no match, else the negative len offset for the match"""
    count = 0
    for y in iterable:
        if y:
            return count
        count += 1
    return -1


def is_cycle(stack, atom, cur_choice, attr):
    # short cut...
    if attr == "post_rdepends":
        # not possible for a cycle we'll care about to exist.
        # the 'cut off' point is for the new atom, thus not possible for
        # a cycle.
        return -1
    
    cycle_start = -1
    for idx, x in enumerate(stack):
        if x.mode == "post_rdepends":
            cycle_start = -1
        if x.atom.key == atom.key:
            cycle_start = idx

    if cycle_start != -1:
        # deque can't be sliced, thus islice
        s = ', '.join('[%s: %s]' % 
            (x.atom, x.current_pkg) for x in islice(stack, cycle_start))
        if s:
            s += ', '
        s += '[%s: %s]' % (atom, cur_choice.current_pkg)
        dprint("%s level cycle: stack: %s\n",
            (attr, s), "cycle")
    return cycle_start


class InconsistantState(Exception):
    pass


class InsolubleSolution(Exception):
    pass


#iter/pkg sorting functions for selection strategy
pkg_sort_highest = partial(sorted, reverse=True)
pkg_sort_lowest = sorted

pkg_grabber = operator.itemgetter(0)

def highest_iter_sort(l):
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


def lowest_iter_sort(l):
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


def default_global_strategy(resolver, dbs, atom):
    return chain(*[repo.match(atom) for repo in dbs])

def default_depset_reorder(resolver, depset, mode):
    for or_block in depset:
        vdb = []
        non_vdb = []
        if len(or_block) == 1:
            yield or_block
            continue
        for atom in or_block:
            if not atom.blocks and caching_iter(
                p for r in resolver.livefs_dbs
                for p in r.match(atom)):
                vdb.append(atom)
            else:
                non_vdb.append(atom)
        if vdb:
            yield vdb + non_vdb
        else:
            yield or_block


class caching_repo(object):

    def __init__(self, db, strategy):
        self.__db__ = db
        self.__strategy__ = strategy
        self.__cache__ = {}

    def match(self, restrict):
        v = self.__cache__.get(restrict)
        if v is None:
            v = self.__cache__[restrict] = \
                caching_iter(self.__db__.itermatch(restrict,
                    sorter=self.__strategy__))
        return v
    
    __getattr__ = GetAttrProxy("__db__")

    def clear(self):
        self.__cache__.clear()


class resolver_frame(object):

    __slots__ = ("atom", "choice_point", "mode",)
    
    def __init__(self, atom, choice_point, mode):
        self.atom = atom
        self.choice_point = choice_point
        self.mode = mode
    
    def __str__(self):
        return "frame: mode %r: atom %s: current %s" % \
            (self.mode, self.atom, self.current_pkg)

    @property
    def current_pkg(self):
        try:
            return self.choice_point.current_pkg
        except IndexError:
            return None


class resolver_stack(deque):

    def __str__(self):
        return 'resolver stack:\n  %s' % '\n  '.join(str(x) for x in self)

    def __repr__(self):
        return '<%s: %r>' % (self.__class__.__name__, 
            tuple(repr(x) for x in self))


class merge_plan(object):

    vdb_restrict = packages.PackageRestriction("repo.livefs",
        values.EqualityMatch(True))

    def __init__(self, dbs, per_repo_strategy,
                 global_strategy=default_global_strategy,
                 depset_reorder_strategy=default_depset_reorder,
                 drop_cycles=False):
        if not isinstance(dbs, (list, tuple)):
            dbs = [dbs]
        self.depset_reorder = depset_reorder_strategy
        self.per_repo_strategy = per_repo_strategy
        self.global_strategy = global_strategy
        self.forced_atoms = set()
        self.all_dbs = [caching_repo(x, self.per_repo_strategy) for x in dbs]
        self.livefs_dbs = [x for x in self.all_dbs if x.livefs]
        self.dbs = [x for x in self.all_dbs if not x.livefs]
        self.state = plan_state()
        self.insoluble = set()
        self.vdb_preloaded = False
        self.drop_cycles = drop_cycles

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

    def process_depends(self, atom, dbs, current_stack, choices, depset,
                        depth=0, drop_cycles=False):
        failure = []
        additions, blocks, = [], []
        dprint("depends:     %s%s: started: %s",
               (depth *2 * " ", atom, choices.current_pkg))
        for datom_potentials in depset:
            failure = []
            for datom in datom_potentials:
                if datom.blocks:
                    # don't register, just do a scan. and this sucks
                    # because any later insertions prior to this won't
                    # get hit by the blocker
                    l = self.state.match_atom(datom)
                    if l:
                        dprint("depends blocker messing with us- "
                               "dumping to pdb for inspection of "
                               "atom %s, pkg %s, ret %s",
                               (atom, choices.current_pkg, l), "blockers")
                        continue
                else:
                    index = is_cycle(current_stack, datom, choices, "depends")
                    if index != -1:
                        # cycle.

#                        v = values.ContainmentMatch(datom, negate=True)
#                        import pdb;pdb.set_trace()
#                        new_atom = packages.AndRestriction(self.current_atom,
#                            PackageRestriction("depends", v),
#                            PackageRestriction("rdepends", v))
#                        import pdb;pdb.set_trace()
                        # reduce our options.
                        failure = self._rec_add_atom(
                            datom, current_stack, self.livefs_dbs,
                            depth=depth+1, mode="depends")
                        if failure and drop_cycles:
                            dprint("depends level cycle: %s: "
                                   "dropping cycle for %s from %s",
                                   (atom, datom, choices.current_pkg), "cycle")
                            failure = []
                            # note we trigger a break ourselves.
                            break
                    else:
                        failure = self._rec_add_atom(
                            datom, current_stack, dbs, depth=depth+1,
                            mode="depends")
                    if failure:
                        dprint("depends:     %s%s: reducing %s from %s",
                               (depth *2 * " ", atom, datom,
                                choices.current_pkg))
                        if choices.reduce_atoms(datom):
                            # this means the pkg just changed under our feet.
                            return [[datom] + failure]
                        continue
                additions.append(datom)
                break
            else: # didn't find any solutions to this or block.
                choices.reduce_atoms(datom_potentials)
                return [datom_potentials]
        else: # all potentials were usable.
            return additions, blocks

    def process_rdepends(self, atom, dbs, current_stack, choices, attr, depset,
                         depth=0, drop_cycles=False):
        failure = []
        additions, blocks, = [], []
        if attr == "post_rdepends":
            dprint("prdepends:   %s%s: started: %s",
                (depth *2 * " ", atom, choices.current_pkg))
        else:
            dprint("%s:    %s%s: started: %s",
                (attr, depth *2 * " ", atom, choices.current_pkg))
        for ratom_potentials in depset:
            failure = []
            for ratom in ratom_potentials:
                if ratom.blocks:
                    blocks.append(ratom)
                    break
                index = is_cycle(current_stack, ratom, choices, attr)
                if index != -1:
                    # cycle.  whee.
                    if dbs is self.livefs_dbs:
                        # well. we know the node is valid, so we can
                        # ignore this cycle.
                        failure = []
                    else:
                        # XXX this is faulty for rdepends/prdepends most likely

                        if current_stack[index].mode == attr:
                            # contained rdepends cycle... ignore it.
                            failure = []
                        else:
                            # force limit_to_vdb to True to try and
                            # isolate the cycle to installed vdb
                            # components
                            failure = self._rec_add_atom(
                                ratom, current_stack, self.livefs_dbs,
                                depth=depth+1, mode=attr)
                            if failure and drop_cycles:
                                dprint("rdepends level cycle: %s: "
                                       "dropping cycle for %s from %s",
                                       (atom, ratom, choices.current_pkg),
                                       "cycle")
                                failure = []
                                break
                else:
                    failure = self._rec_add_atom(ratom, current_stack, dbs,
                                                 depth=depth+1, mode=attr)
                if failure:
                    # reduce.
                    if choices.reduce_atoms(ratom):
                        # pkg changed.
                        return [[ratom] + failure]
                    continue
                additions.append(ratom)
                break
            else: # didn't find any solutions to this or block.
                choices.reduce_atoms(ratom_potentials)
                return [ratom_potentials]
        else: # all potentials were usable.
            return additions, blocks

    def insert_choice(self, atom, current_stack, choices):
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
                        self.state.add_pkg(choice_point(slotted_atom, m),
                                           force=True)
                        break

        # first, check for conflicts.
        l = self.state.add_pkg(choices)
        # lil bit fugly, but works for the moment
        if l:
            # this means in this branch of resolution, someone slipped
            # something in already. cycle, basically.
            dprint("was trying to insert atom '%s' pkg '%s',\n"
                   "but '[%s]' exists already", (atom, choices.current_pkg,
                                                 ", ".join(str(y) for y in l)))
            # hack.  see if what was insert is enough for us.

            # this is tricky... if it's the same node inserted
            # (cycle), then we ignore it; this does *not* perfectly
            # behave though, doesn't discern between repos.
            if (len(l) == 1 and l[0] == choices.current_pkg and
                l[0].repo.livefs == choices.current_pkg.repo.livefs and
                atom.match(l[0])):
                # early exit. means that a cycle came about, but exact
                # same result slipped through.
                dprint("non issue, cycle for %s pkg %s resolved to same pkg" %
                       (repr(atom), choices.current_pkg))
                return False
            try_rematch = False
            if any(True for x in l if isinstance(x, restriction.base)):
                # blocker was caught
                dprint("blocker detected in slotting, trying a re-match")
                try_rematch = True
            elif not any (True for x in l if not self.vdb_restrict.match(x)):
                # vdb entry, replace.
                if self.vdb_restrict.match(choices.current_pkg):
                    # we're replacing a vdb entry with a vdb entry?  wtf.
                    print ("internal weirdness spotted, "
                           "dumping to pdb for inspection")
                    import pdb;pdb.set_trace()
                    raise Exception()
                dprint("replacing a vdb node, so it's valid (need to do a "
                       "recheck of state up to this point however, which "
                       "we're not)")
                l = self.state.add_pkg(choices, REPLACE)
                if l:
                    dprint("tried the replace, but got matches still- %s", l)
            else:
                try_rematch = True
            if try_rematch:
                l2 = self.state.match_atom(atom)
                if l2 == [choices.current_pkg]:
                    dprint("node was pulled in already, same so ignoring it")
                    # stop resolution.
                    l = False
                elif l2:
                    dprint("and we 'parently match it.  ignoring "
                           "(should prune here however)")
                    # need to do cleanup here
#                    import pdb;pdb.set_trace()
                    l = False

        else:
            l = None
        return l

    def _rec_add_atom(self, atom, current_stack, dbs, depth=0, mode="none",
                      drop_cycles=False):
        """Add an atom.

        @return: False on no issues (inserted succesfully),
            else a list of the stack that screwed it up.
        """
        limit_to_vdb = dbs == self.livefs_dbs

        if atom in self.insoluble:
            dprint("processing   %s%s: marked insoluble already",
                   (depth *2 * " ", atom))
            return [atom]
        l = self.state.match_atom(atom)
        if l:
            if current_stack:
                dprint("pre-solved  %s%s, [%s] [%s]",
                       (((depth*2) + 1)*" ", atom, current_stack[-1].atom,
                        ", ".join(str(x) for x in l)), 'pre-solved')
            else:
                dprint("pre-solved %s%s, [%s]",
                       (depth*2*" ", atom, ", ".join(str(x) for x in l)),
                       'pre-solved')
            return False
        # not in the plan thus far.
        matches = caching_iter(self.global_strategy(self, dbs, atom))
        if matches:
            choices = choice_point(atom, matches)
            # ignore what dropped out, at this juncture we don't care.
            choices.reduce_atoms(self.insoluble)
            if not choices:
                s = 'first level'
                if current_stack:
                    s = current_stack[-1].atom
                dprint("filtering    %s%s  [%s] reduced it to no matches",
                       (depth * 2 * " ", atom, s))
                matches = None
                # and was intractable because it has a hard dep on an
                # unsolvable atom.
        if not matches:
            if not limit_to_vdb:
                self.insoluble.add(atom)
            s = 'first level'
            if current_stack:
                s = current_stack[-1].atom
            dprint("processing   %s%s  [%s] no matches",
                   (depth *2 * " ", atom, s))
            return [atom]

        # experiment. ;)
        # see if we can insert or not at this point (if we can't, no
        # point in descending)

        if current_stack:
            if limit_to_vdb:
                dprint("processing   %s%s  [%s]; mode %s vdb bound",
                       (depth *2 * " ", atom, current_stack[-1].atom, mode))
            else:
                dprint("processing   %s%s  [%s]; mode %s",
                       (depth *2 * " ", atom, current_stack[-1].atom, mode))
        else:
            dprint("processing   %s%s", (depth *2 * " ", atom))

        current_stack.append(resolver_frame(atom, choices, mode))
        saved_state = self.state.current_state()

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

            l = self.process_depends(
                atom, dbs, current_stack, choices,
                self.depset_reorder(self, choices.depends, "depends"),
                depth=depth, drop_cycles=drop_cycles)
            if len(l) == 1:
                dprint("reseting for %s%s because of depends: %s",
                       (depth*2*" ", atom, l[0][-1]))
                self.state.reset_state(saved_state)
                failures = l[0]
                continue
            additions += l[0]
            blocks += l[1]

            l = self.process_rdepends(
                atom, dbs, current_stack, choices, "rdepends",
                self.depset_reorder(self, choices.rdepends, "rdepends"),
                depth=depth, drop_cycles=drop_cycles)
            if len(l) == 1:
                dprint("reseting for %s%s because of rdepends: %s",
                       (depth*2*" ", atom, l[0]))
                self.state.reset_state(saved_state)
                failures = l[0]
                continue
            additions += l[0]
            blocks += l[1]

            dprint("choose for   %s%s, %s",
                   (depth *2*" ", atom, choices.current_pkg))

            l = self.insert_choice(atom, current_stack, choices)
            if l is False:
                # this means somehow the node already slipped in.
                # so we exit now, we are satisfied
                current_stack.pop()
                return False
            elif l is not None:
                # failure.
                self.state.reset_state(saved_state)
                choices.force_next_pkg()
                continue

            # level blockers.
            fail = True
            for x in blocks:
                # hackity hack potential- say we did this-
                # disallowing blockers from blocking what introduced them.
                # iow, we can't block ourselves (can block other
                # versions, but not our exact self)
                # this might be suspect mind you...
                # disabled, but something to think about.
                
                # check for any matches; none, try and insert vdb nodes.
                if not self.vdb_preloaded and \
                    not choices.current_pkg.repo.livefs and \
                    not self.state.match_atom(x):
                    for repo in self.livefs_dbs:
                        m = repo.match(x)
                        if m:
                            dprint("inserting vdb node for blocker"
                                " %s %s" % (x, m[0]))
                            self.state.add_pkg(choice_point(x, m),
                                force=True)
                            break;
                    
                l = self.state.add_blocker(choices, 
                    self.generate_mangled_blocker(choices, x), key=x.key)
                if l:
                    # blocker caught something. yay.
                    dprint("rdepend blocker %s hit %s for atom %s pkg %s",
                           (x, l, atom, choices.current_pkg))
                    failures = [x]
                    break
            else:
                fail = False
            if fail:
                choices.reduce_atoms(x)
                self.state.reset_state(saved_state)
                continue

            fail = True
            for x in choices.provides:
                l = self.state.add_provider(choices, x)
                if l and l != [x]:
                    if len(current_stack) > 1:
                        if not current_stack[-2].atom.match(x):
                            print "provider conflicted... how?"
#                            import pdb;pdb.set_trace()
#                            print "should do something here, something sane..."
                            fail = [x]
                            break
            else:
                fail = False
            if fail:
                self.state.reset_state(saved_state)
                choices.force_next_pkg()
                continue

            # reset blocks for pdepend proccesing
            blocks = []
            l = self.process_rdepends(
                atom, dbs, current_stack, choices, "post_rdepends",
                self.depset_reorder(self, choices.post_rdepends,
                                    "post_rdepends"),
                depth=depth, drop_cycles=drop_cycles)

            if len(l) == 1:
                dprint("reseting for %s%s because of rdepends: %s",
                       (depth*2*" ", atom, l[0]))
                self.state.reset_state(saved_state)
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
                    dprint("rdepend blocker %s hit %s for atom %s pkg %s",
                           (x, l, atom, choices.current_pkg))
                    failures = [x]
                    break
            else:
                fail = False
            if fail:
                self.state.reset_state(saved_state)
                choices.force_next_pkg()
                continue
            break

        else:
            dprint("no solution  %s%s", (depth*2*" ", atom))
            current_stack.pop()
            self.state.reset_state(saved_state)
            # saving roll.  if we're allowed to drop cycles, try it again.
            # this needs to be *far* more fine grained also. it'll try
            # regardless of if it's cycle issue
            if not drop_cycles and self.drop_cycles:
                dprint("trying saving throw for %s ignoring cycles",
                       atom, "cycle")
                # note everything is retored to a pristine state prior also.
                l = self._rec_add_atom(atom, current_stack, dbs, depth=depth,
                                       mode=mode, drop_cycles=True)
                if not l:
                    return False
            return [atom] + failures

        current_stack.pop()
        return False

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
    def prefer_livefs_dbs(dbs):
        for r in dbs:
            if r.livefs:
                yield r
        for r in dbs:
            if not r.livefs:
                yield r

    @staticmethod
    def prefer_highest_version_strategy(self, dbs, atom):
        # XXX rework caching_iter so that it iter's properly
        return iter_sort(highest_iter_sort,
                         *[repo.match(atom)
                         for repo in self.prefer_livefs_dbs(dbs)])
        #return iter_sort(highest_iter_sort,
        #                 default_global_strategy(self, dbs, atom))

    @staticmethod
    def prefer_lowest_version_strategy(self, dbs, atom):
        return iter_sort(lowest_iter_sort,
                         default_global_strategy(self, dbs, atom))

    @staticmethod
    def prefer_reuse_strategy(self, dbs, atom):
        for r in self.prefer_livefs_dbs(dbs):
            for p in r.match(atom):
                yield p

    def generic_force_version_strategy(self, vdb, dbs, atom, iter_sorter,
                                       pkg_sorter):
        try:
            # nasty, but works.
            yield iter_sort(iter_sorter,
                            *[r.itermatch(atom, sorter=pkg_sorter)
                              for r in [vdb] + dbs]).next()
#            yield max(itertools.chain(*[r.itermatch(atom)
#                                        for r in [vdb] + dbs]))
        except StopIteration:
            # twas no matches
            pass

    force_max_version_strategy = staticmethod(
        post_curry(generic_force_version_strategy,
                   highest_iter_sort, pkg_sort_highest))
    force_min_version_strategy = staticmethod(
        post_curry(generic_force_version_strategy,
                   lowest_iter_sort, pkg_sort_lowest))

REMOVE  = 0
ADD     = 1
REPLACE = 2
FORWARD_BLOCK = 3
REMOVE_FORWARD_BLOCK = 4
state_ops = {ADD:"add",
    REMOVE:"remove",
    REPLACE:"replace",
    FORWARD_BLOCK:None,
    REMOVE_FORWARD_BLOCK:None
}

class plan_state(object):
    def __init__(self):
        self.state = PigeonHoledSlots()
        self.plan = []
        self.pkg_choices = {}
        self.rev_blockers = {}

    def add_pkg(self, choices, action=ADD, force=False):
        return self._add_pkg(choices, choices.current_pkg, action, force=force)

    def add_provider(self, choices, provider, action=ADD):
        return self._add_pkg(choices, provider, action)

    def _add_pkg(self, choices, pkg, action, force=False):
        """returns False (no issues), else the conflicts"""
        if action == ADD:
            l = self.state.fill_slotting(pkg, force=force)
            if l:
                return l
            self.plan.append((action, choices, force, pkg))
            self.pkg_choices[pkg] = choices
        elif action == REMOVE:
            # level it even if it's not existant?
            self.state.remove_slotting(pkg)
            self.plan.append((action, choices, force, pkg))
            del self.pkg_choices[pkg]
        elif action == REPLACE:
            l = self.state.fill_slotting(pkg)
            assert len(l) == 1
            self.state.remove_slotting(l[0])
            l2 = self.state.fill_slotting(pkg, force=force)
            if l2:
                #revert
                l3 = self.state.fill_slotting(l[0])
                assert not l3
                return l2

            self.plan.append((action, choices, force, pkg, l[0],
                self.pkg_choices[l[0]]))
            # wipe the to-be-replaced pkgs blockers
            self._remove_pkg_blockers(self.pkg_choices[l[0]])
            del self.pkg_choices[l[0]]
            self.pkg_choices[pkg] = choices
        return False

    def _remove_pkg_blockers(self, choices):
        l = self.rev_blockers.get(choices, None)
        if l is None:
            return
        for blocker, key in l:
            self.plan.append(
                (REMOVE_FORWARD_BLOCK, choices, blocker, key))
            self.state.remove_limiter(blocker, key)
        del self.rev_blockers[choices]
        
    def reset_state(self, state_pos):
        assert state_pos <= len(self.plan)
        if len(self.plan) == state_pos:
            return
        pkg_choices = self.pkg_choices
        rev_blockers = self.rev_blockers
        for change in reversed(self.plan[state_pos:]):
            if change[0] == ADD:
                self.state.remove_slotting(change[3])
                del pkg_choices[change[3]]
            elif change[0] == REMOVE:
                self.state.fill_slotting(change[3], force=change[2])
                pkg_choices[change[3]] = change[2]
            elif change[0] == REPLACE:
                self.state.remove_slotting(change[3])
                self.state.fill_slotting(change[4], force=change[3])
                del pkg_choices[change[3]]
                pkg_choices[change[4]] = change[5]
            elif change[0] == FORWARD_BLOCK:
                self.state.remove_limiter(change[2], key=change[3])
                l = [x for x in rev_blockers[change[1]]
                    if x[0] != change[2]]
                if l:
                    rev_blockers[change[1]] = l
                else:
                    del rev_blockers[change[1]]
            elif change[0] == REMOVE_FORWARD_BLOCK:
                self.rev_blockers.setdefault(change[1],
                    []).append((change[2], change[3]))
            else:
                raise AssertionError(
                    "encountered unknown command reseting state: %r" %
                    change)
        self.plan = self.plan[:state_pos]

    def iter_pkg_ops(self):
        for x in self.plan:
            assert x[0] in state_ops
            val = state_ops[x[0]]
            if val is None:
                continue
            if x[0] == REPLACE:
                yield val, x[3:5]
            else:
                yield val, x[3:]

    def add_blocker(self, choices, blocker, key=None):
        """adds blocker, returning any packages blocked"""
        l = self.state.add_limiter(blocker, key=key)
        self.plan.append((FORWARD_BLOCK, choices, blocker, key))
        self.rev_blockers.setdefault(choices, []).append((blocker, key))
        return l

    def match_atom(self, atom):
        return self.state.find_atom_matches(atom)

    def pkg_conflicts(self, pkg):
        return self.state.get_conflicting_slot(pkg)

    def current_state(self):
        #hack- this doesn't work when insertions are possible
        return len(self.plan)
