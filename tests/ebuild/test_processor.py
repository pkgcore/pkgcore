import os
import signal
import subprocess
import sys
import textwrap
import threading

import pytest

from pkgcore.ebuild import processor
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.processor import EbuildProcessor
from pkgcore.pytest.plugin import EbuildRepo


class TestEnvironmentDump:
    def test_multibyte_function_body(self, repo):
        # raw non-ASCII in a function body makes the receive_env byte count
        # exceed the char count; reading as text over-read past the payload
        # (https://bugs.gentoo.org/930852)
        data = 'src_prepare() {\n\techo "café résumé naïve größe" || die\n}\n'
        repo.create_ebuild("cat/pkg-1", data=data)
        repo.sync()
        pkg = max(repo.itermatch(atom("cat/pkg")))
        env = pkg.environment.text_fileobj().read()
        assert "café résumé naïve größe" in env


def test_metadata_from_non_ascii_repo_path(tmp_path):
    repo = EbuildRepo(str(tmp_path / "תיקייה"))
    (tmp_path / "תיקייה" / "eclass" / "foo.eclass").write_text("foo() { :; }\n")
    repo.create_ebuild("cat/pkg-1", eapi="8", data="inherit foo\n")
    repo.sync()
    pkg = max(repo.itermatch(atom("cat/pkg")))
    assert list(pkg.inherited) == ["foo"]


def test_send_env_after_env_sets_utf8_locale():
    env = {"LC_ALL": "C.UTF-8", "X": "תיקייה"}
    ebp = processor.request_ebuild_processor(sandbox=False)
    results = []

    def send():
        ebp.write("process_ebuild setup")
        results.extend(ebp.send_env(env) for _ in range(2))

    try:
        t = threading.Thread(target=send, daemon=True)
        t.start()
        t.join(10)
        assert results == [True, True]
    finally:
        processor.drop_ebuild_processor(ebp)
        ebp.shutdown_processor(force=True)


class TestGenerateEnvStr:
    def _gen(self, env):
        # _generate_env_str only needs _readonly_vars; avoid spawning a daemon.
        proc = EbuildProcessor.__new__(EbuildProcessor)
        proc._readonly_vars = frozenset()
        return proc._generate_env_str(env)

    def test_all_exported_without_marker(self):
        # absent PKGCORE_NONEXPORTED_VARS everything is exported on a single line
        out = self._gen({"P": "foo-1", "PATH": "/bin", "arr": ["x", "y"]})
        assert "\n" not in out
        assert out.startswith("export ")
        assert "P='foo-1'" in out
        assert 'arr=([0]="x" [1]="y")' in out

    def test_nonexported_split(self):
        out = self._gen(
            {
                "PKGCORE_NONEXPORTED_VARS": "P ARCH USE SLOT",
                "P": "foo-1",
                "ARCH": "amd64",
                "USE": "a b",
                "SLOT": "0",
                "PATH": "/bin",
                "HOME": "/tmp/h",
                "D": "/img/",
            }
        )
        plain_line, export_line = out.splitlines()
        assert not plain_line.startswith("export ")
        assert export_line.startswith("export ")
        # marked variables are bare assignments (unexported shell vars)
        for assign in ("ARCH=amd64", "P='foo-1'", "SLOT=0", "USE='a b'"):
            assert assign in plain_line
            assert assign not in export_line
        # everything else stays exported
        for assign in ("D='/img/'", "HOME='/tmp/h'", "PATH='/bin'"):
            assert assign in export_line
        # the marker itself never leaks
        assert "PKGCORE_NONEXPORTED_VARS" not in out

    def test_marker_only_nonexported(self):
        # when nothing is exported there is no export line
        out = self._gen({"PKGCORE_NONEXPORTED_VARS": "P", "P": "foo-1"})
        assert out == "P='foo-1'"

    def test_values_round_trip_through_bash(self):
        val = "it's C:\\new $HOME `id`\n"
        out = self._gen({"V": val})
        res = subprocess.run(
            ["bash", "-c", f'{out}\nprintf %s "$V"'],
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout == val


class TestSandboxSummary:
    def test_move_log(self, tmp_path):
        log = tmp_path / "sandbox.log"
        log.write_text("open_wr: /etc/passwd\n")
        moved = tmp_path / "moved.log"
        proc = object.__new__(EbuildProcessor)
        proc._EbuildProcessor__sandbox_log = str(log)
        written = []
        proc.write = written.append
        assert proc.sandbox_summary(move_log=str(moved)) == 1
        assert moved.read_text() == "open_wr: /etc/passwd\n"
        assert written[-1] == "end_sandbox_summary"


class TestClearPreloadedEclasses:
    def test_processor_survives(self):
        ebp = processor.request_ebuild_processor()
        try:
            assert ebp.clear_preloaded_eclasses()
            assert ebp.is_alive
        finally:
            processor.drop_ebuild_processor(ebp)
            ebp.shutdown_processor()


def test_is_responsive_disarms_timeout_with_async_expects(tmp_path):
    eclass = tmp_path / "foo.eclass"
    eclass.write_text("foo() { :; }\n")
    ebp = processor.request_ebuild_processor()
    try:
        assert ebp._preload_eclass(str(eclass), async_req=True)
        assert ebp.is_responsive
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        processor.drop_ebuild_processor(ebp)
        ebp.shutdown_processor()


def test_unresponsive_daemon_is_killed_on_shutdown(monkeypatch):
    def hung(*args):
        raise AssertionError("shutdown waited on an unresponsive daemon")

    ebp = processor.request_ebuild_processor()
    processor.drop_ebuild_processor(ebp)
    proc = ebp._proc
    monkeypatch.setattr(EbuildProcessor, "is_responsive", property(lambda s: False))
    old = signal.signal(signal.SIGALRM, hung)
    signal.alarm(10)
    try:
        ebp.shutdown_processor()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert ebp.ebd_write.closed and ebp.ebd_read.closed


def test_ebd_sigterm_while_holding_processor_lock():
    ebp = processor.request_ebuild_processor()

    def handle():
        # the SIGTERM and die() handlers run while request_ebuild_processor()
        # or shutdown_all_processors() already hold the lock
        with processor._global_ebp_lock:
            processor.chuck_TermInterrupt(ebp)

    t = threading.Thread(target=handle, daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive()
    assert not ebp.is_alive


def test_reuse_processor_from_worker_thread():
    ebp = processor.request_ebuild_processor()
    processor.release_ebuild_processor(ebp)
    got = []
    t = threading.Thread(
        target=lambda: got.append(processor.request_ebuild_processor())
    )
    t.start()
    t.join(30)
    try:
        assert len(got) == 1 and got[0].is_alive
    finally:
        for x in got:
            processor.release_ebuild_processor(x)


def test_expect_timeout_kills_unresponsive_daemon():
    ebp = processor.request_ebuild_processor()
    processor.drop_ebuild_processor(ebp)
    os.killpg(ebp.pid, signal.SIGSTOP)
    ebp.write("alive")
    results = []

    def expect():
        results.append(ebp.expect("yep!", timeout=0.5))

    try:
        t = threading.Thread(target=expect, daemon=True)
        t.start()
        t.join(10)
        assert results == [False]
        assert not ebp.is_alive
    finally:
        ebp.shutdown_processor(force=True)


@pytest.mark.skipif(not hasattr(signal, "sigtimedwait"), reason="no sigtimedwait")
def test_write_to_dead_daemon_raises_with_default_sigpipe():
    # pkgcore scripts run with SIGPIPE at SIG_DFL (snakeoil.cli.tool)
    script = textwrap.dedent(
        """
        import os, signal, time
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        from pkgcore.ebuild import processor
        ebp = processor.request_ebuild_processor()
        processor.drop_ebuild_processor(ebp)
        os.killpg(ebp.pid, signal.SIGKILL)
        # the sandbox's bash child may hold the pipe open a little longer
        for _ in range(100):
            try:
                ebp.write("alive")
            except RuntimeError:
                print("raised")
                break
            time.sleep(0.1)
        ebp.shutdown_processor(force=True)
        """
    )
    ret = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (ret.returncode, ret.stdout) == (0, "raised\n")
