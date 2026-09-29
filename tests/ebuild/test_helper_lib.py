import os
import subprocess

from pkgcore import const

HELPER_LIB = os.path.join(const.EBD_PATH, "helpers", "internals", "helper-lib.bash")


def run_helper(script, nonfatal):
    stubs = 'die() { echo "died: $*"; exit 99; }\neerror() { echo "eerror: $*"; }\n'
    return subprocess.run(
        ["bash", "-c", f"{stubs}source {HELPER_LIB}\n{script}"],
        env={"PKGCORE_NONFATAL": nonfatal, "HELPER_ERROR_PREFIX": "newins"},
        capture_output=True,
        text=True,
    )


class TestCheckCommandOrStop:
    def test_nonfatal(self):
        proc = run_helper("check_command_or_stop false", "true")
        assert proc.returncode == 1
        assert (
            "eerror: newins: exitcode 1: false failed, cannot continue" in proc.stdout
        )

    def test_fatal(self):
        proc = run_helper("check_command_or_stop false", "false")
        assert proc.returncode == 99
        assert "died: newins: exitcode 1: false failed" in proc.stdout

    def test_success(self):
        proc = run_helper("check_command_or_stop true; echo ok", "false")
        assert proc.returncode == 0
        assert proc.stdout == "ok\n"
