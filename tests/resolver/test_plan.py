import pytest
from pkgcore.resolver import plan
from pkgcore.test.misc import FakePkg


@pytest.mark.parametrize(("sorter", "vers", "expected", "iter_sort_target"), (
    pytest.param(plan.highest_iter_sort, [7,9,3,2], [9,7,3,2], True, id="highest iter"),
    pytest.param(plan.lowest_iter_sort, [7,9,4,2], [2,4,7,9], True, id="lowest iter"),
    pytest.param(plan.pkg_sort_highest, [1,9,7,10], [10,9,7,1], False, id="pkg highest"),
    pytest.param(plan.pkg_sort_lowest, [11,9,1,6], [1,6,9,11], False, id="pkg lowest"),
))
def test_pkg_sorting(sorter, vers, expected, iter_sort_target):
    pkgs = [FakePkg(f"d-b/a-{x}") for x in vers]
    if iter_sort_target:
        pkgs = [[x, []] for x in pkgs]
    pkgs = list(sorter(pkgs))
    if iter_sort_target:
        pkgs = [x[0] for x in pkgs]
    assert [int(x.fullver) for x in pkgs] == expected
