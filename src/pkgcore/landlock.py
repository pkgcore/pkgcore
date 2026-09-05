"""Self-confinement with the Linux Landlock LSM.

Generating metadata means sourcing ebuilds with bash, which runs code out of the
repo it came from with whatever access the invoking user has.  :py:func:`confine`
takes away what that doesn't need: everything stays readable and executable, but
writes are denied outside the paths the caller names, as is outgoing TCP.

Restrictions cannot be lifted and are inherited by every thread and process
started afterwards, so only call this from a command's main function, in a
process meant to stay confined for the rest of its life.  In particular, never
call it from library code whose caller carries on working once the ebuilds have
been sourced.

Landlock mediates TCP bind and connect only, leaving UDP, ICMP and unix sockets
untouched, so this is not an exfiltration boundary.  Access through an already
open descriptor is unaffected as well, since rights are checked when a path is
resolved rather than on the descriptor.
"""

__all__ = ("confine", "writable_cache_paths")

import os
import tempfile
from collections.abc import Iterator

from .exceptions import PkgcoreUserException
from .log import logger

try:
    from py_landlock import AccessFs, Landlock, LandlockError

    # Rights granted on a writable directory and everything beneath it.  Fifos
    # and sockets are included for the sake of the temp dir: bash falls back to
    # a named pipe for process substitution when built without /dev/fd support,
    # and multiprocessing uses a unix socket for non-fork start methods.
    _DIR_RW = (
        AccessFs.READ_FILE
        | AccessFs.READ_DIR
        | AccessFs.WRITE_FILE
        | AccessFs.TRUNCATE
        | AccessFs.MAKE_REG
        | AccessFs.MAKE_DIR
        | AccessFs.MAKE_SYM
        | AccessFs.MAKE_FIFO
        | AccessFs.MAKE_SOCK
        | AccessFs.REMOVE_FILE
        | AccessFs.REMOVE_DIR
        | AccessFs.REFER
        | AccessFs.EXECUTE
    )
    # Rights granted on a writable file.  Directory-only rights have to be left
    # out: the kernel rejects the entire rule for a non-directory rather than
    # ignoring the ones that don't apply.  Ioctls matter only for the device
    # nodes below, and only for ones opened after the ruleset applies --
    # inherited descriptors such as a terminal on stdin are never affected.
    _FILE_RW = (
        AccessFs.READ_FILE
        | AccessFs.WRITE_FILE
        | AccessFs.TRUNCATE
        | AccessFs.IOCTL_DEV
    )
except ImportError:  # pragma: no cover
    Landlock = None


def _ebd_paths() -> Iterator[str]:
    """Paths that sourcing an ebuild needs to be able to write, whatever else does."""
    # The ebuild daemon is handed a minimal environment, so the bash sourcing
    # ebuilds never sees a redirected TMPDIR and falls back to the system one.
    # Here-documents too big for a pipe land there.
    yield tempfile.gettempdir()
    # opened read-write by subprocess.DEVNULL, among others
    yield os.devnull
    # where sandbox(1) reports access violations; losing them would hide the
    # very misbehaviour worth knowing about, and the inherited output
    # descriptors already point at the same terminal
    yield "/dev/tty"


def writable_cache_paths(*repos) -> Iterator[str]:
    """Cache locations pkgcore may write while generating metadata for *repos*.

    Repos whose cache is already read-only are skipped, so passing every repo
    involved in a run grants no more than pkgcore would have written anyway.
    """
    for repo in repos:
        for cache in getattr(repo, "cache", ()):
            if cache.readonly:
                continue
            # pkgcore creates a missing cache dir on demand and decides
            # writability from the closest existing parent, so grant that
            path = cache.location
            while not os.path.exists(path):
                if (parent := os.path.dirname(path)) == path:
                    break
                path = parent
            yield path


def _unavailable(required: bool, msg: str) -> bool:
    """Fail or note that confinement couldn't be set up."""
    if required:
        raise PkgcoreUserException(f"sandbox unavailable: {msg}")
    logger.debug("skipping landlock confinement: %s", msg)
    return False


def confine(*writable: str, allow_net: bool = False, required: bool = False) -> bool:
    """Deny writes outside *writable*, and outgoing TCP unless *allow_net*.

    The paths sourcing an ebuild needs are always granted on top of *writable*.
    A path that doesn't exist is skipped, and rights the kernel won't accept for
    a non-directory are dropped rather than failing the whole rule.

    :param required: raise rather than carry on unconfined when landlock is
        unavailable, too old, or disabled at boot.
    :raises PkgcoreUserException: if *required* and the restrictions couldn't be
        applied.
    :return: whether the restrictions were applied.
    """
    if Landlock is None:
        return _unavailable(required, "py-landlock is not installed")

    try:
        sandbox = Landlock(strict=False)
        # scoping signals and abstract sockets isn't what this is for
        sandbox.allow_all_scope()
        if allow_net:
            sandbox.allow_all_network()
        # the whole filesystem stays readable and executable; this only takes
        # away the ability to write to it
        sandbox.add_path_rule(
            "/", access=AccessFs.READ_FILE | AccessFs.READ_DIR | AccessFs.EXECUTE
        )
        for path in (*writable, *_ebd_paths()):
            if os.path.isdir(path):
                sandbox.add_path_rule(path, access=_DIR_RW)
            elif os.path.exists(path):
                sandbox.add_path_rule(path, access=_FILE_RW)
            else:
                logger.debug("landlock: no such path, skipping: %r", path)
        sandbox.apply()
    except (LandlockError, OSError) as e:
        return _unavailable(required, str(e))

    logger.debug("landlock confinement applied, ABI %s", sandbox.abi_version)
    return True
