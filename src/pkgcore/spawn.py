"""Bash and sandbox support for running commands.

Commands are spawned with :py:mod:`subprocess`; what lives here is what it has
no opinion about: where bash and sandbox are, the argv that runs a command
under either, and probes for the system bash version and for whether the host
can sandbox or drop privileges at all.

:py:func:`bash_command` and :py:func:`sandbox_command` only build an argv --
the caller spawns it, keeping file descriptors, environment and privileges in
its own hands.
"""

__all__ = (
    "BASH_BINARY",
    "SANDBOX_BINARY",
    "bash_command",
    "bash_version",
    "is_sandbox_capable",
    "is_userpriv_capable",
    "sandbox_command",
)

import os
import subprocess
from collections.abc import Iterable, Sequence
from functools import cache

from snakeoil.process import find_binary

BASH_BINARY = find_binary("bash", fallback="/bin/bash")
SANDBOX_BINARY = find_binary("sandbox", fallback="/usr/bin/sandbox")


def bash_command(command: str | Iterable[str], debug: bool = False) -> list[str]:
    """Build the argv running ``command`` under a bash ignoring its rc files."""
    args = [BASH_BINARY, "--norc", "--noprofile"]
    if debug:
        args.append("-x")
    args.append("-c")
    if isinstance(command, str):
        args.append(command)
    else:
        args.extend(command)
    return args


def sandbox_command(command: Sequence[str]) -> list[str]:
    """Build the argv running ``command`` under sandbox.

    The caller is expected to have checked :py:func:`is_sandbox_capable` first.
    """
    return [SANDBOX_BINARY, *command]


@cache
def bash_version() -> str | None:
    """The system bash version, of the form major.minor.patch."""
    try:
        ret = subprocess.run(
            bash_command(
                "printf ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}.${BASH_VERSINFO[2]}"
            ),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if ret.returncode:
        return None
    return ret.stdout or None


@cache
def is_sandbox_capable() -> bool:
    """Can a sandboxed process be spawned?"""
    if "SANDBOX_ACTIVE" in os.environ:
        # a sandbox cannot be spawned inside another one
        return False
    if not (os.path.isfile(SANDBOX_BINARY) and os.access(SANDBOX_BINARY, os.X_OK)):
        return False
    try:
        ret = subprocess.run(
            [SANDBOX_BINARY, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return ret.returncode == 0 and "gentoo" in ret.stdout.lower()


@cache
def is_userpriv_capable() -> bool:
    """Can this process drop to another uid/gid?"""
    return os.getuid() == 0
