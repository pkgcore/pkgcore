from functools import partial, total_ordering

import pytest
from pkgcore.package.base import base, dynamic_getattr_dict
from pkgcore.package.mutated import MutatedPkg


def passthru(val, self):
    return val


@total_ordering
class FakePkg(base):
    # XXX why isn't this using existing classes?
    __slotting_intentionally_disabled__ = True

    def __init__(self, pkg, ver, data):
        base.__init__(self)
        self.pkg = pkg
        self.ver = ver
        self._get_attr = {k: partial(passthru, v) for k, v in data.items()}

    # disable protection.  don't want it here
    __setattr__ = object.__setattr__
    __getattr__ = dynamic_getattr_dict

    def __lt__(self, other):
        return self.ver < other.ver


class TestMutatedPkg:
    def make_fakepkg(self, pkg="dar", ver=1, data=None):
        if data is None:
            data = {"a": 1}
        return FakePkg(pkg, ver, data)

    def test_raw_pkg(self):
        pkg = self.make_fakepkg()
        assert MutatedPkg(pkg, {})._raw_pkg is pkg

    def test_cmp(self):
        pkg1 = self.make_fakepkg()
        pkg2 = self.make_fakepkg(ver=2)
        mpkg1 = MutatedPkg(pkg1, {})
        mpkg2 = MutatedPkg(pkg2, {})

        for lpkg in (pkg1, mpkg1):
            assert lpkg < mpkg2
            assert mpkg2 > lpkg
        assert mpkg1 == mpkg1
        assert pkg1 == mpkg1

    def test_getattr(self):
        pkg = self.make_fakepkg()
        assert MutatedPkg(pkg, {}).a == 1
        assert MutatedPkg(pkg, {"a": 2}).a == 2
        with pytest.raises(AttributeError):
            getattr(MutatedPkg(pkg, {}), "b")
