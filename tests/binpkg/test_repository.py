from types import SimpleNamespace

from pkgcore.binpkg.repository import BinPkg, force_unpacking
from pkgcore.merge import engine


class TestBinPkg:
    def test_add_format_triggers(self, monkeypatch):
        registered = []
        monkeypatch.setattr(force_unpacking, "register", registered.append)
        pkg = SimpleNamespace(
            repo=object(),
            mandatory_phases=(),
            eapi=SimpleNamespace(options=SimpleNamespace(rewrite_image_symlinks=False)),
        )
        engine_inst = SimpleNamespace(mode=engine.INSTALL_MODE, new=pkg)
        op_inst = SimpleNamespace(format_op=object())
        factory = object.__new__(BinPkg)
        factory._add_format_triggers(pkg, op_inst, object(), engine_inst)
        assert len(registered) == 1
