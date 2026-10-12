import gc
import warnings

from pkgcore.binpkg import xpak

DATA = {"CATEGORY": "dev-util", "PF": "foo-1"}


def mk_xpak(tmp_path):
    (path := tmp_path / "foo-1.tbz2").write_bytes(b"")
    xpak.Xpak.write_xpak(str(path), DATA)
    return str(path)


def test_round_trip(tmp_path):
    x = xpak.Xpak(mk_xpak(tmp_path))
    assert dict(x.items()) == DATA
    assert x["PF"] == "foo-1"


def test_closes_files(tmp_path):
    path = mk_xpak(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        x = xpak.Xpak(path)
        list(x.keys())
        x["CATEGORY"]
        list(x.items())
        list(x.values())
        del x
        gc.collect()
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_caller_handle_left_open(tmp_path):
    with open(mk_xpak(tmp_path), "rb") as f:
        assert dict(xpak.Xpak(f).items()) == DATA
        assert not f.closed
