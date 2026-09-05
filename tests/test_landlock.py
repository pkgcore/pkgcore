import errno
import os
import socket
import sys
import tempfile
from functools import partial

import pytest
from snakeoil.cli.arghparse import Namespace

from pkgcore import landlock
from pkgcore.exceptions import PkgcoreUserException


def run_confined(func, *writable, **kwargs):
    """Run *func* in a forked child confined to *writable*.

    Confinement can't be undone, so it never touches the test session itself.
    Returns the child's stringified result, or its error.
    """
    read_fd, write_fd = os.pipe()
    if (pid := os.fork()) == 0:  # pragma: no cover
        os.close(read_fd)
        try:
            landlock.confine(*writable, **kwargs)
            os.write(write_fd, str(func()).encode())
        except BaseException as e:
            os.write(write_fd, f"error: {e!r}".encode())
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    with os.fdopen(read_fd) as f:
        output = f.read()
    os.waitpid(pid, 0)
    return output


def write_denied(path):
    """Whether the kernel refuses to create a file under *path*."""
    try:
        with open(os.path.join(path, "probe"), "w") as f:
            f.write("data")
    except PermissionError:
        return True
    return False


def read_file(path):
    """Read a byte back, to show reads survive confinement."""
    with open(path, "rb") as f:
        return bool(f.read(1))


def tcp_denied():
    """Whether the kernel refuses an outgoing TCP connection.

    Landlock rejects the connect before any packet leaves, so the discard port
    needs nothing listening on it.
    """
    with socket.socket() as s:
        try:
            s.connect(("127.0.0.1", 9))
        except PermissionError:
            return True
        except OSError:
            return False
    return False


def repo(**kwargs):
    """A stand-in carrying just the cache attribute confine() reads."""
    return Namespace(**kwargs)


@pytest.fixture
def landlock_kernel():
    """Skip unless the running kernel actually enforces Landlock."""
    py_landlock = pytest.importorskip("py_landlock")
    try:
        py_landlock.get_abi_version()
    except py_landlock.LandlockError as e:
        pytest.skip(f"landlock unavailable: {e}")


@pytest.fixture
def tmpdir(tmp_path, monkeypatch):
    """Move the system temp dir somewhere under tmp_path.

    confine() always grants the real one, which contains tmp_path itself, so
    without this everything the tests write to would sit inside an allowed path.
    """
    (path := tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(path))
    return path


class TestWritableCachePaths:
    def test_no_cache_attr(self):
        assert list(landlock.writable_cache_paths(repo())) == []

    def test_readonly_skipped(self, tmp_path):
        cache = Namespace(location=str(tmp_path), readonly=True)
        assert list(landlock.writable_cache_paths(repo(cache=(cache,)))) == []

    def test_writable(self, tmp_path):
        cache = Namespace(location=str(tmp_path), readonly=False)
        assert list(landlock.writable_cache_paths(repo(cache=(cache,)))) == [
            str(tmp_path)
        ]

    def test_missing_walks_up_to_existing_parent(self, tmp_path):
        location = str(tmp_path / "metadata" / "md5-cache")
        cache = Namespace(location=location, readonly=False)
        assert list(landlock.writable_cache_paths(repo(cache=(cache,)))) == [
            str(tmp_path)
        ]

    def test_several_repos(self, tmp_path):
        (a := tmp_path / "a").mkdir()
        (b := tmp_path / "b").mkdir()
        repos = [
            repo(cache=(Namespace(location=str(a), readonly=False),)),
            repo(cache=(Namespace(location=str(b), readonly=True),)),
        ]
        assert list(landlock.writable_cache_paths(*repos)) == [str(a)]


class TestAvailability:
    def test_unavailable_best_effort(self, monkeypatch):
        monkeypatch.setattr(landlock, "Landlock", None)
        assert landlock.confine() is False

    def test_unavailable_but_required(self, monkeypatch):
        monkeypatch.setattr(landlock, "Landlock", None)
        with pytest.raises(PkgcoreUserException, match="sandbox unavailable"):
            landlock.confine(required=True)

    def test_applied(self, landlock_kernel, tmpdir):
        assert run_confined(lambda: landlock.confine.__name__) == "confine"


class TestConfinement:
    def test_outside_write_denied(self, tmp_path, landlock_kernel, tmpdir):
        (outside := tmp_path / "outside").mkdir()
        assert run_confined(partial(write_denied, outside)) == "True"

    def test_granted_path_writable(self, tmp_path, landlock_kernel, tmpdir):
        (allowed := tmp_path / "allowed").mkdir()
        assert run_confined(partial(write_denied, allowed), str(allowed)) == "False"

    def test_missing_path_skipped(self, tmp_path, landlock_kernel, tmpdir):
        missing = str(tmp_path / "nonexistent")
        assert run_confined(lambda: "ran", missing) == "ran"

    def test_tmpdir_always_granted(self, tmp_path, landlock_kernel, tmpdir):
        # the bash sourcing ebuilds falls back to it for big here-documents
        assert run_confined(partial(write_denied, tmpdir)) == "False"

    def test_devnull_always_granted(self, landlock_kernel, tmpdir):
        # subprocess.DEVNULL opens it read-write
        def check():
            os.close(os.open(os.devnull, os.O_RDWR))
            return True

        assert run_confined(check) == "True"

    def test_devtty_always_granted(self, landlock_kernel, tmpdir):
        # where sandbox(1) reports access violations
        def check():
            try:
                os.close(os.open("/dev/tty", os.O_WRONLY))
            except OSError as e:
                # no controlling terminal, but landlock let the open through
                return e.errno == errno.ENXIO
            return True

        assert run_confined(check) == "True"

    def test_reads_still_allowed(self, landlock_kernel, tmpdir):
        assert run_confined(partial(read_file, sys.executable)) == "True"


class TestNetworkConfinement:
    def test_tcp_denied(self, landlock_kernel, tmpdir):
        assert run_confined(tcp_denied) == "True"

    def test_tcp_allowed(self, landlock_kernel, tmpdir):
        assert run_confined(tcp_denied, allow_net=True) == "False"
