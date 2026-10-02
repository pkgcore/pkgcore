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

    def test_directory_without_recursive(self, tmp_path):
        image = tmp_path / "image"
        (tmp_path / "dir").mkdir()
        (tmp_path / "bar").write_text("bar")
        op = FakeOp(FakePkg("cat/pkg-1", eapi="8"), FakeDomain([]))
        op.ED = str(image)
        with pytest.raises(ebd_ipc.IpcCommandError, match="missing -r"):
            self.run(ebd_ipc.Doins(op), tmp_path, "dir")
        self.run(ebd_ipc.Doins(op), tmp_path, "dir", "bar")
        assert (image / "usr/share/foo/bar").read_text() == "bar"
        assert not (image / "usr/share/foo/dir").exists()


class FakeObserver:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class TestEapplyUser:
    def test_ignores_eapply_options(self, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return ebd_ipc.subprocess.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(ebd_ipc.subprocess, "run", fake_run)
        patch = tmp_path / "user.patch"
        patch.write_text("")
        op = FakeOp(FakePkg("cat/pkg-1", eapi="8"), FakeDomain([]))
        op.observer = FakeObserver()
        op.userpriv = False
        eapply = ebd_ipc.Eapply(op)
        eapply.opts = ebd_ipc.arghparse.Namespace()
        eapply.run(eapply.parse_args([], ["-p0", str(patch)]))
        eapply.run([(None, [str(patch)])], user=True)
        assert "-p0" in calls[0]
        assert "-p0" not in calls[1]


class TestEapply:
    def test_directory_is_not_recursed(self, tmp_path):
        patches = tmp_path / "patches"
        (patches / "sub").mkdir(parents=True)
        (patches / "nested.patch").mkdir()
        for name in ("b.diff", "a.patch", "README", "sub/c.patch"):
            (patches / name).write_text("")
        op = FakeOp(FakePkg("cat/pkg-1", eapi="8"), FakeDomain([]))
        eapply = ebd_ipc.Eapply(op)
        eapply.opts = ebd_ipc.arghparse.Namespace()
        assert list(eapply.parse_args([], [str(patches)])) == [
            (str(patches), [str(patches / "a.patch"), str(patches / "b.diff")])
        ]

    def test_directory_without_patches(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.patch").write_text("")
        op = FakeOp(FakePkg("cat/pkg-1", eapi="8"), FakeDomain([]))
        eapply = ebd_ipc.Eapply(op)
        eapply.opts = ebd_ipc.arghparse.Namespace()
        with pytest.raises(ebd_ipc.IpcCommandError, match="no patches in directory"):
            list(eapply.parse_args([], [str(tmp_path)]))


def test_multi_line_reply_stays_on_one_line():
    ret = ebd_ipc.IpcCommand._encode_ret((1, "install: cannot stat 'x'\n  hint\n"))
    assert ret == "1\x07install: cannot stat 'x'; hint"
    assert ebd_ipc.IpcCommand._encode_ret("a\nb") == "0\x07a; b"


@pytest.mark.parametrize(
    ("eapi", "args", "installed"),
    (
        ("8", ["foo.1"], "man1/foo.1"),
        ("8", ["foo.fr.1"], "fr/man1/foo.1"),
        ("8", ["-i18n=de", "foo.1"], "de/man1/foo.1"),
        ("8", ["-i18n=de", "foo.fr.1"], "de/man1/foo.fr.1"),
        ("8", ["-i18n=", "foo.fr.1"], "man1/foo.fr.1"),
        ("3", ["-i18n=de", "foo.fr.1"], "fr/man1/foo.1"),
        ("3", ["-i18n=de", "foo.1"], "de/man1/foo.1"),
        ("0", ["-i18n=de", "foo.fr.1"], "de/man1/foo.fr.1"),
    ),
)
def test_doman_i18n(tmp_path, eapi, args, installed):
    (tmp_path / args[-1]).write_text("man page")
    image = tmp_path / "image"
    op = FakeOp(FakePkg("cat/pkg-1", eapi=eapi), FakeDomain([]))
    op.ED = str(image)
    cmd = ebd_ipc.Doman(op)
    cmd.opts = ebd_ipc.arghparse.Namespace()
    with chdir(tmp_path):
        cmd.run(cmd.parse_args(["--dest=/usr/share/man"], args))
    assert (image / "usr/share/man" / installed).read_text() == "man page"


def test_links_use_image_paths(tmp_path):
    image = tmp_path / "image"
    (image / "usr/share/foo").mkdir(parents=True)
    (image / "bin").mkdir()
    (image / "bin/a").write_text("a")
    op = FakeOp(FakePkg("cat/pkg-1", eapi="3"), FakeDomain([]))
    op.ED = str(image)

    def run(kls, *args):
        cmd = kls(op)
        cmd.opts = ebd_ipc.arghparse.Namespace()
        cmd.run(cmd.parse_args([], list(args)))

    run(ebd_ipc.Dosym, "foo", "/usr/lib")
    assert (image / "usr/lib").is_symlink()
    with pytest.raises(ebd_ipc.IpcCommandError, match="missing filename"):
        run(ebd_ipc.Dosym, "foo", "/usr/share/foo")
    run(ebd_ipc.Dohard, "/bin/a", "/bin/b")
    assert (image / "bin/a").samefile(image / "bin/b")
