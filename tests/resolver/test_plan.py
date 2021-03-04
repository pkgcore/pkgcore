from snakeoil.currying import post_curry
from snakeoil.test import TestCase

from pkgcore.resolver import plan
from pkgcore.test.misc import FakePkg


class TestPkgSorting(TestCase):

    def check_it(self, sorter, vers, expected, iter_sort_target=False):
        pkgs = [FakePkg(f"d-b/a-{x}") for x in vers]
        if iter_sort_target:
            pkgs = [[x, []] for x in pkgs]
        pkgs = list(sorter(pkgs))
        if iter_sort_target:
            pkgs = [x[0] for x in pkgs]
        self.assertEqual([int(x.fullver) for x in pkgs], expected)

    test_highest_iter_sort = post_curry(check_it, plan.highest_iter_sort,
        [7,9,3,2], [9,7,3,2], True)

    test_lowest_iter_sort = post_curry(check_it, plan.lowest_iter_sort,
        [7,9,4,2], [2,4,7,9], True)

    test_pkg_sort_highest = post_curry(check_it, plan.pkg_sort_highest,
        [1,9,7,10], [10,9,7,1])

    test_pkg_sort_lowest = post_curry(check_it, plan.pkg_sort_lowest,
        [11,9,1,6], [1,6,9,11])
