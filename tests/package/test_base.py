from functools import partial
from types import SimpleNamespace

import pytest
from pkgcore.package import base


def fake_pkg(cat='dev-util', pkg='bsdiff', ver='1.0', **attrs):
    attrs.setdefault('category', cat)
    attrs.setdefault('pkg', pkg)
    attrs.setdefault('ver', ver)
    attrs.setdefault('key', f"{cat}/{pkg}")
    attrs.setdefault('cpvstr', f"{cat}/{pkg}-{ver}")
    attrs.setdefault('built', False)
    return SimpleNamespace(**attrs)


class mixin:

    def mk_inst(self):
        raise NotImplementedError(self, "mk_inst")

    def test_setattr(self):
        with pytest.raises(AttributeError):
            setattr(self.mk_inst(), "asdf", 1)

    def test_delattr(self):
        with pytest.raises(AttributeError):
            delattr(self.mk_inst(), "asdf")


class TestBasePkg(mixin):

    mk_inst = kls = staticmethod(base.base)

    def test_properties(self):
        o = self.kls()
        for f in ("versioned_atom", "unversioned_atom"):
            with pytest.raises(NotImplementedError):
                getattr(o, f)
            with pytest.raises(AttributeError):
                o.__setattr__(f, "a")
            with pytest.raises(AttributeError):
                o.__delattr__(f)

    def test_getattr(self):
        class Class(base.base):
            __slotting_intentionally_disabled__ = True
            _get_attr = {str(x): partial((lambda a, s: a), x)
                         for x in range(10)}
            _get_attr["a"] = lambda s:"foo"
            __getattr__ = base.dynamic_getattr_dict

        o = Class()
        for x in range(10):
            assert getattr(o, str(x)) == x
        assert o.a == "foo"
        assert not self.mk_inst().built


class TestWrapper(mixin):

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
        assert not self.mk_inst().built
        assert self.mk_inst(built=True).built
        # verify that wrapping will override it
        assert not self.mk_inst(overrides={'built':False}, built=True).built
