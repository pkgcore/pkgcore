from snakeoil.mappings import AttrAccessible

from pkgcore import log
from pkgcore.restrictions import packages, values
from pkgcore.test import (TestCase, TestRestriction, callback_logger,
                          malleable_obj, silence_logging)


class AlwaysSelfIntersect(values.base):
    def intersect(self, other):
        return self

    __hash__ = object.__hash__


class TestPackageRestriction(TestRestriction):

    if packages.PackageRestriction is packages.PackageRestriction:
        kls = packages.PackageRestriction
    else:
        class kls(packages.PackageRestriction,
            packages.PackageRestriction_mixin):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestriction.__inst_caching__

    kls = staticmethod(kls)

    @silence_logging(log.logging.root)
    def test_matching(self):
        strexact = values.StrExactMatch

        args = malleable_obj(category="foon", package="dar")
        self.assertMatches(self.kls("category", strexact("foon")), args)
        self.assertMatches(self.kls("package", strexact("dar")), args)
        self.assertNotMatches(self.kls("package", strexact("dar"), negate=True),
            args)
        self.assertNotMatches(self.kls("package", strexact("foon")), args)

        self.assertMatches(self.kls("package", strexact("foon"), negate=True),
            args)
        excepts = []
        # no msg should be thrown, it wasn't an unexpected exception

        log.logging.root.addHandler(callback_logger(excepts.append))
        self.assertNotMatches(self.kls("foon", AlwaysSelfIntersect), args)
        self.assertFalse(excepts)

        self.assertMatches(self.kls("foon", AlwaysSelfIntersect, negate=True),
            args)
        self.assertFalse(excepts)

        class foo:
            def __getattr__(self, attr):
                if attr.startswith("exc"):
                    raise exceptions_d.get(attr[4:], None)()
                raise AttributeError("monkey lover")

        exceptions_d = {"KeyboardInterrupt":KeyboardInterrupt,
            "RuntimeError":RuntimeError, "SystemExit":SystemExit}

        for mode in ("match", "force_True", "force_False"):
            excepts[:] = []
            self.assertRaises(AttributeError,
                getattr(self.kls("foon", AlwaysSelfIntersect), mode),
                foo())
            self.assertEqual(
                len(excepts), 1,
                msg=f"expected one exception, got {excepts!r}")

            # ensure various exceptions are passed through
            for k in (KeyboardInterrupt, RuntimeError, SystemExit):
                self.assertRaises(
                    k,
                    getattr(self.kls(f"exc_{k.__name__}", AlwaysSelfIntersect), mode),
                    foo())

        # check that it only does string comparison in exception catching.
        class foo:
            def __cmp__(self, other):
                raise TypeError

            def __getattr__(self, attr):
                raise AttributeError(self, attr)

        self.assertFalse(self.kls("foon", AlwaysSelfIntersect).match(foo()))

    def test_attr(self):
        self.assertEqual(self.kls('val', values.AlwaysTrue).attr,
            'val')
        self.assertEqual(self.kls('val.dar', values.AlwaysTrue).attr,
            'val.dar')
        self.assertEqual(self.kls('val', values.AlwaysTrue).attrs,
            ('val',))
        self.assertEqual(self.kls('val.dar', values.AlwaysTrue).attrs,
            ('val.dar',))

    def test_eq(self):
        self.assertEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue))
        self.assertNotEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('one', values.AlwaysTrue, negate=True))
        self.assertNotEqual(
            self.kls('one', values.AlwaysTrue),
            self.kls('two', values.AlwaysTrue))
        self.assertNotEqual(
            self.kls('one', values.AlwaysTrue, negate=True),
            self.kls('one', values.AlwaysFalse, negate=True))

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


class TestPackageRestrictionMulti(TestCase):

    if packages.PackageRestriction is packages.PackageRestriction:
        kls = packages.PackageRestrictionMulti
    else:
        class kls(packages.PackageRestrictionMulti,
            packages.PackageRestrictionMulti_mixin):
            __slots__ = ()
            __inst_caching__ = packages.PackageRestrictionMulti.__inst_caching__

    kls = staticmethod(kls)

    def test_attr(self):
        o = self.kls(("asdf.far", "repo"), values.AlwaysTrue)
        self.assertEqual(o.attrs, ("asdf.far", "repo"))
        self.assertEqual(o.attr, None)

    def test_values(self):
        l = []
        def f(*args):
            self.assertLen(args, 1)
            l.append(args[0])
            return True

        o = self.kls(("asdf.far", "repo"), values_callback(f))

        pkg = AttrAccessible()
        o.match(pkg)
        self.assertFalse(l)

        pkg['repo'] = 1
        o.match(pkg)
        self.assertFalse(l)

        pkg['asdf'] = AttrAccessible(far=2)
        o.match(pkg)
        self.assertEqual(l, [(None, [2,1],)])

        l[:] = []
        o.force_True(pkg)
        self.assertEqual(l, [(True, pkg, ('asdf.far', 'repo'), [2,1],)])

        l[:] = []
        o.force_False(pkg)
        self.assertEqual(l, [(False, pkg, ('asdf.far', 'repo'), [2,1],)])


class ConditionalTest(TestCase):

    def test_eq(self):
        p = (packages.PackageRestriction('one', values.AlwaysTrue),)
        p2 = (packages.PackageRestriction('one', values.AlwaysFalse),)
        v = values.AlwaysTrue
        v2 = values.AlwaysFalse
        self.assertEqual(
            packages.Conditional('use', v, p),
            packages.Conditional('use', v, p))
        self.assertNotEqual(
            packages.Conditional('use', v2, p),
            packages.Conditional('use', v, p))
        self.assertNotEqual(
            packages.Conditional('use', v, p),
            packages.Conditional('use', v, p2))
        self.assertNotEqual(
            packages.Conditional('use1', v, p),
            packages.Conditional('use', v, p))
