from types import SimpleNamespace

from pkgcore.vdb import repo_ops


class TestInstall:
    def test_pkg_without_ebuild(self, tmp_path):
        vdb = tmp_path / "vdb"
        vdb.mkdir()
        repo = SimpleNamespace(location=str(vdb), lock=None, _metadata_rewrites={})
        pkg = SimpleNamespace(
            tracked_attributes=(),
            category="cat",
            package="pkg",
            fullver="1",
            PF="pkg-1",
            ebuild=None,
        )
        op = repo_ops.install(repo, pkg, None)
        assert op.add_data(SimpleNamespace(pm_tmpdir=str(tmp_path / "tmp")))
        assert (vdb / "cat" / ".tmp.pkg-1" / "pkg-1.ebuild").read_bytes() == b""
