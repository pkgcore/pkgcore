from types import SimpleNamespace

import pytest
from pkgcore.restrictions import packages, values
from snakeoil.mappings import AttrAccessible

from .utils import TestRestriction


class AlwaysSelfIntersect(values.base):
    def intersect(self, other):
        return self

    __hash__ = object.__hash__


class TestPackageRestriction(TestRestriction):

    if packages.PackageRestriction is packages.PackageRestriction:
        kls = packages.PackageRestriction
    else:
        class kls(packages.PackageRestriction, packages.PackageRestriction_mixin):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestriction.__inst_caching__

    kls = staticmethod(kls)

    def test_matching(self, caplog):
        strexact = values.StrExactMatch

        args = SimpleNamespace(category="foon", package="dar")
        self.assertMatches(self.kls("category", strexact("foon")), args)
        self.assertMatches(self.kls("package", strexact("dar")), args)
        self.assertNotMatches(self.kls("package", strexact("dar"), negate=True), args)
        self.assertNotMatches(self.kls("package", strexact("foon")), args)

        self.assertMatches(self.kls("package", strexact("foon"), negate=True), args)

        # no msg should be thrown, it wasn't an unexpected exception
        caplog.clear()
        self.assertNotMatches(self.kls("foon", AlwaysSelfIntersect), args)
        assert not caplog.records

        self.assertMatches(self.kls("foon", AlwaysSelfIntersect, negate=True), args)
        assert not caplog.records

        class foo:
            def __getattr__(self, attr):
                if attr.startswith("exc"):
                    raise exceptions_d.get(attr[4:], None)()
                raise AttributeError("monkey lover")

        exceptions_d = {"KeyboardInterrupt":KeyboardInterrupt,
            "RuntimeError":RuntimeError, "SystemExit":SystemExit}

        for mode in ("match", "force_True", "force_False"):
            caplog.clear()
            with pytest.raises(AttributeError):
                getattr(self.kls("foon", AlwaysSelfIntersect), mode)(foo())
            assert len(caplog.records) == 1

            # ensure various exceptions are passed through
            for k in (KeyboardInterrupt, RuntimeError, SystemExit):
                with pytest.raises(k):
                    getattr(self.kls(f"exc_{k.__name__}", AlwaysSelfIntersect), mode)(foo())

        # check that it only does string comparison in exception catching.
        class foo:
            def __cmp__(self, other):
                raise TypeError

            def __getattr__(self, attr):
                raise AttributeError(self, attr)

        assert not self.kls("foon", AlwaysSelfIntersect).match(foo())

    @pytest.mark.parametrize('value', ('val', 'val.dar'))
    def test_attr(self, value):
        assert self.kls(value, values.AlwaysTrue).attr == value
        assert self.kls(value, values.AlwaysTrue).attrs == (value,)

    def test_eq(self):
        assert self.kls('one', values.AlwaysTrue) == self.kls('one', values.AlwaysTrue)
        assert self.kls('one', values.AlwaysTrue) != self.kls('one', values.AlwaysTrue, negate=True)
        assert self.kls('one', values.AlwaysTrue) != self.kls('two', values.AlwaysTrue)
        assert self.kls('one', values.AlwaysTrue, negate=True) != self.kls('one', values.AlwaysFalse, negate=True)

    def test_hash(self):
        inst = self.kls('one.dar', AlwaysSelfIntersect())
        hash(inst)


class values_callback(values.base):

    __slots__ = ("callback",)

    def __init__(self, callback):
        object.__setattr__(self, 'callback', callback)

    def match(self, val):
        return self.callback((None, val))

    def force_True(self, pkg, attr, val):
        return self.callback((True, pkg, attr, val))

    def force_False(self, pkg, attr, val):
        return self.callback((False, pkg, attr, val))


class TestPackageRestrictionMulti:

    if packages.PackageRestriction is packages.PackageRestriction:
        kls = packages.PackageRestrictionMulti
    else:
        class kls(packages.PackageRestrictionMulti, packages.PackageRestrictionMulti_mixin):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestrictionMulti.__inst_caching__

    kls = staticmethod(kls)

    def test_attr(self):
        o = self.kls(("asdf.far", "repo"), values.AlwaysTrue)
        assert o.attrs == ("asdf.far", "repo")
        assert o.attr is None

    def test_values(self):
        l = []
        def f(*args):
            assert len(args) == 1
            l.append(args[0])
            return True

        o = self.kls(("asdf.far", "repo"), values_callback(f))

        pkg = AttrAccessible()
        o.match(pkg)
        assert not l

        pkg['repo'] = 1
        o.match(pkg)
        assert not l

        pkg['asdf'] = AttrAccessible(far=2)
        o.match(pkg)
        assert l == [(None, [2, 1],)]

        l.clear()
        o.force_True(pkg)
        assert l == [(True, pkg, ('asdf.far', 'repo'), [2, 1],)]

        l.clear()
        o.force_False(pkg)
        assert l == [(False, pkg, ('asdf.far', 'repo'), [2, 1],)]


def test_conditional():
    p = (packages.PackageRestriction('one', values.AlwaysTrue),)
    p2 = (packages.PackageRestriction('one', values.AlwaysFalse),)
    v = values.AlwaysTrue
    v2 = values.AlwaysFalse
    assert packages.Conditional('use', v, p) == packages.Conditional('use', v, p)
    assert packages.Conditional('use', v2, p) != packages.Conditional('use', v, p)
    assert packages.Conditional('use', v, p) != packages.Conditional('use', v, p2)
    assert packages.Conditional('use1', v, p) != packages.Conditional('use', v, p)
