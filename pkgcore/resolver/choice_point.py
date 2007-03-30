# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


from snakeoil.lists import iter_stable_unique

class choice_point(object):

    __slots__ = (
        "__weakref__", "atom", "matches", "matches_cur", "solution_filters",
        "_prdeps", "_rdeps", "_deps", "_provides")

    def __init__(self, a, matches):
        self.atom = a
        self.matches = iter(matches)
        self.matches_cur = None
        self.solution_filters = set()
        # match solutions, remaining
        self._deps = None
        self._rdeps = None
        self._prdeps = None
        self._provides = None

    @property
    def state(self):
        m = self.matches_cur
        return (len(self.solution_filters),
            m.repo, m,
            self.matches,
            self._deps,
            self._rdeps,
            self._prdeps)

    @staticmethod
    def _filter_choices(cnf_reqs, filterset):
        for choices in cnf_reqs:
            l = [x for x in choices if x not in filterset]
            if not l:
                return
            yield l

    def _internal_force_next(self):
        """
        force next pkg without triggering a reduce_atoms call
        @return: True if pkgs remain, False if no more remain
        """
        for self.matches_cur in self.matches:
            self._reset_iters()
            return True
        self.matches_cur = self.matches = None
        return False

    def reduce_atoms(self, atom):

        if self.matches is None:
            raise IndexError("no solutions remain")
        if hasattr(atom, "__contains__") and not isinstance(atom, basestring):
            self.solution_filters.update(atom)
        else:
            self.solution_filters.add(atom)

        filterset = self.solution_filters
        if self.matches_cur is None:
            if not self._internal_force_next():
                return True

        round = -1
        while True:
            round += 1
            if round:
                if not self._internal_force_next():
                    return True

            reqs = list(self._filter_choices(self._deps, filterset))
            if len(reqs) != len(self._deps):
                continue
            self._deps = reqs

            reqs = list(self._filter_choices(self._rdeps, filterset))
            if len(reqs) != len(self._rdeps):
                continue
            self._rdeps = reqs

            reqs = list(self._filter_choices(self._prdeps, filterset))
            if len(reqs) != len(self._prdeps):
                continue
            self._prdeps = reqs

            return round > 0
        return True

    def _reset_iters(self):
        cur = self.matches_cur
        self._deps = cur.depends.cnf_solutions()
        self._rdeps = cur.rdepends.cnf_solutions()
        self._prdeps = cur.post_rdepends.cnf_solutions()
        self._provides = tuple(iter_stable_unique(cur.provides))

    @property
    def slot(self):
        return self.current_pkg.slot

    @property
    def key(self):
        return self.current_pkg.key

    @property
    def current_pkg(self):
        if self.matches_cur is None:
            if self.matches is None:
                raise IndexError("no packages remain")
            for self.matches_cur in self.matches:
                break
            else:
                self.matches = None
                raise IndexError("no more packages remain")
            self._reset_iters()
        return self.matches_cur

    def force_next_pkg(self):
        if self.matches is None:
            return False
        for self.matches_cur in self.matches:
            break
        else:
            self.matches_cur = self.matches = None
            return False
        return self.reduce_atoms([])

    @property
    def depends(self):
        if not self:
            raise IndexError("no more solutions remain")
        return self._deps

    @property
    def rdepends(self):
        if not self:
            raise IndexError("no more solutions remain")
        return self._rdeps

    @property
    def post_rdepends(self):
        if not self:
            raise IndexError("no more solutions remain")
        return self._prdeps

    @property
    def provides(self):
        if not self:
            raise IndexError("no more solutions remain")
        return self._provides

    def __nonzero__(self):
        if self.matches_cur is None:
            if self.matches is None:
                return False
            for self.matches_cur in self.matches:
                break
            else:
                self.matches = None
                return False
            self._reset_iters()
        return True
