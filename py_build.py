import os
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from flit_core import buildapi


@contextmanager
def sys_path():
    orig_path = sys.path[:]
    sys.path.insert(0, str(Path.cwd() / "src"))
    try:
        yield
    finally:
        sys.path = orig_path


def write_pkgcore_lookup_configs(cleanup_files):
    """Generate file of install path constants."""
    cleanup_files.append(path := Path.cwd() / "src/pkgcore/_const.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"writing lookup config to {path}")

    with open(path, "w") as f:
        os.chmod(path, 0o644)
        f.write(
            textwrap.dedent(
                """\
            from os.path import abspath, exists, join
            import sys

            INSTALL_PREFIX = abspath(sys.prefix)
            if not exists(join(INSTALL_PREFIX, 'lib/pkgcore')):
                INSTALL_PREFIX = abspath(sys.base_prefix)
            DATA_PATH = join(INSTALL_PREFIX, 'share/pkgcore')
            CONFIG_PATH = join(DATA_PATH, 'config')
            LIBDIR_PATH = join(INSTALL_PREFIX, 'lib/pkgcore')
            EBD_PATH = join(LIBDIR_PATH, 'ebd')
            INJECTED_BIN_PATH = ()
        """
            )
        )


def write_verinfo(cleanup_files):
    cleanup_files.append(path := Path.cwd() / "src/pkgcore/_verinfo.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"generating version info: {path}")
    from snakeoil.version import get_git_version

    path.write_text(f"version_info={get_git_version(Path.cwd())!r}")


def prepare_pkgcore(callback, consts: bool):
    cleanup_files = []
    try:
        with sys_path():
            write_verinfo(cleanup_files)

            # Install configuration data so pkgcore knows where to find its content,
            # rather than assuming it is running from a tarball/git repo.
            if consts:
                write_pkgcore_lookup_configs(cleanup_files)

            # generate function lists so they don't need to be created on install
            if subprocess.call(
                [
                    "make",
                    f"PYTHON={sys.executable}",
                    "PYTHONPATH=" + ":".join(sys.path),
                ],
                cwd=Path.cwd() / "data/lib/pkgcore/ebd",
            ):
                raise Exception("Running makefile failed")

            return callback()
    finally:
        for path in cleanup_files:
            try:
                path.unlink()
            except OSError:
                pass


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Builds a wheel, places it in wheel_directory"""
    callback = partial(
        buildapi.build_wheel, wheel_directory, config_settings, metadata_directory
    )
    return prepare_pkgcore(callback, consts=True)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    """Builds an "editable" wheel, places it in wheel_directory"""
    callback = partial(
        buildapi.build_editable, wheel_directory, config_settings, metadata_directory
    )
    return prepare_pkgcore(callback, consts=False)


def build_sdist(sdist_directory, config_settings=None):
    """Builds an sdist, places it in sdist_directory"""
    callback = partial(buildapi.build_sdist, sdist_directory, config_settings)
    return prepare_pkgcore(callback, consts=False)
