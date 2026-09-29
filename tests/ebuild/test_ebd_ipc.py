from contextlib import chdir

import pytest

from pkgcore.ebuild import ebd_ipc
from pkgcore.test.misc import FakePkg, FakeRepo


class FakeDomain:
    def __init__(self, installed, root="/"):
        self.all_installed_repos = FakeRepo(installed)
        self.root = root


class FakeOp:
    def __init__(self, pkg, domain, env=None):
        self.pkg = pkg
        self.domain = domain
        self.observer = None
        self.env = env or {}


def _has_version(querying_pkg, installed, atom_str, dep_opts=()):
    op = FakeOp(querying_pkg, FakeDomain(installed), env={"EPREFIX": ""})
    cmd = ebd_ipc.Has_Version(op)
    cmd.opts = ebd_ipc.arghparse.Namespace()
    args = cmd.parse_args([], [*dep_opts, atom_str])
    return cmd.run(args)


class TestQueryCmdConditionalUseDeps:
    """tests for https://github.com/pkgcore/pkgcore/issues/442"""

    def test_conditional_use_dep_matches_enabled(self):
        querying = FakePkg("gnome-base/librsvg-2.58.5", eapi="5", use=["abi_x86_64"])
        installed = (
            FakePkg(
                "dev-lang/rust-bin-1.84.1-r1",
                slot="1.84.1",
                iuse=["abi_x86_64", "abi_x86_32"],
                use=["abi_x86_64"],
            ),
        )
        atom_str = "dev-lang/rust-bin:1.84.1[abi_x86_64(-)?,abi_x86_32(-)?]"
        assert _has_version(querying, installed, atom_str) == 0

    def test_conditional_use_dep_no_match(self):
        querying = FakePkg("gnome-base/librsvg-2.58.5", eapi="5", use=["abi_x86_64"])
        installed = (
            FakePkg(
                "dev-lang/rust-bin-1.84.1-r1",
                slot="1.84.1",
                iuse=["abi_x86_64", "abi_x86_32"],
                use=[],
            ),
        )
        atom_str = "dev-lang/rust-bin:1.84.1[abi_x86_64(-)?]"
        assert _has_version(querying, installed, atom_str) == 1

    def test_conditional_use_dep_bdepend(self):
        querying = FakePkg("gnome-base/librsvg-2.58.5", eapi="8", use=["abi_x86_64"])
        installed = (
            FakePkg(
                "dev-lang/rust-bin-1.84.1-r1",
                slot="1.84.1",
                iuse=["abi_x86_64", "abi_x86_32"],
                use=["abi_x86_64"],
            ),
        )
        atom_str = "dev-lang/rust-bin:1.84.1[abi_x86_64(-)?,abi_x86_32(-)?]"
        assert _has_version(querying, installed, atom_str, dep_opts=["-b"]) == 0

    def test_plain_atom_unaffected(self):
        querying = FakePkg("cat/pkg-1", eapi="5")
        installed = (FakePkg("dev-lang/rust-bin-1.84.1-r1", slot="1.84.1"),)
        assert _has_version(querying, installed, "dev-lang/rust-bin") == 0
        assert _has_version(querying, installed, "dev-lang/nonexistent") == 1


class TestDoins:
    def run(self, cmd, tmp_path, *targets):
        cmd.opts = ebd_ipc.arghparse.Namespace()
        with chdir(tmp_path):
            args = cmd.parse_args(["--dest=/usr/share/foo"], list(targets))
            return cmd.run(args)

    def test_failure_leaves_later_calls_working(self, tmp_path):
        image = tmp_path / "image"
        dest = image / "usr/share/foo"
        (dest / "foo").mkdir(parents=True)
        (tmp_path / "foo").write_text("foo")
        (tmp_path / "bar").write_text("bar")
        op = FakeOp(FakePkg("cat/pkg-1", eapi="8"), FakeDomain([]))
        op.ED = str(image)
        cmd = ebd_ipc.Doins(op)
        with pytest.raises(ebd_ipc.IpcCommandError, match="failed removing file"):
            self.run(cmd, tmp_path, "foo")
        self.run(cmd, tmp_path, "bar")
        assert (dest / "bar").read_text() == "bar"
