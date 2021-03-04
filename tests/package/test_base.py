from functools import partial

from snakeoil.test import TestCase

from pkgcore.package import base
from pkgcore.test import malleable_obj


def fake_pkg(cat='dev-util', pkg='bsdiff', ver='1.0', **attrs):
    d = {}
    d['category'] = cat
    d['pkg'] = pkg
    d['ver'] = ver
    d['key'] = f"{cat}/{pkg}"
    d["cpvstr"] = f"{cat}/{pkg}-{ver}"
    d['built'] = False
    d.update(attrs)
    return malleable_obj(**d)


class mixin:

    def mk_inst(self):
        raise NotImplementedError(self, "mk_inst")

    def test_setattr(self):
        self.assertRaises(AttributeError, setattr,
            self.mk_inst(), "asdf", 1)

    def test_delattr(self):
        self.assertRaises(AttributeError, delattr,
            self.mk_inst(), "asdf")


class TestBasePkg(mixin, TestCase):

    mk_inst = kls = staticmethod(base.base)

    def test_properties(self):
        o = self.kls()
        for f in ("versioned_atom", "unversioned_atom"):
            self.assertRaises(NotImplementedError, getattr, o, f)
            self.assertRaises(AttributeError, o.__setattr__, f, "a")
            self.assertRaises(AttributeError, o.__delattr__, f)

    def test_getattr(self):
        class Class(base.base):
            __slotting_intentionally_disabled__ = True
            _get_attr = {str(x): partial((lambda a, s: a), x)
                         for x in range(10)}
            _get_attr["a"] = lambda s:"foo"
            __getattr__ = base.dynamic_getattr_dict

        o = Class()
        for x in range(10):
            self.assertEqual(getattr(o, str(x)), x)
        self.assertEqual(o.a, "foo")
        self.assertEqual(self.mk_inst().built, False)


class TestWrapper(mixin, TestCase):

    kls = base.wrapper

    def mk_inst(self, overrides=None, **kwds):
        kls = self.kls
        if overrides:
            class kls(self.kls):
                locals().update(overrides)
                __slots__ = ()

        pkg = fake_pkg(**kwds)
        return kls(pkg)

    def test_built_passthru(self):
        # test pass thrus
        self.assertEqual(self.mk_inst().built, False)
        self.assertEqual(self.mk_inst(built=True).built, True)
        # verify that wrapping will override it
        self.assertEqual(self.mk_inst(overrides={'built':False},
            built=True).built, False)
