"""
Binpkg repository operations for modification, maintenance, etc.

This modules specific operation implementations- said operations are
derivatives of :py:mod:`pkgcore.operations.repo` classes.

Generally speaking you only need to dig through this module if you're trying to
modify a binpkg repository operation- changing how it installs, or changing how
it uninstalls, or adding a new operation (cleaning/cache regen for example).
"""

__all__ = ("install", "uninstall", "replace", "operations")

import os

from snakeoil.compression import compress_data
from snakeoil.klass import steal_docs
from snakeoil.osutils import ensure_dirs, pjoin, unlink_if_exists

from ..fs import tar
from ..log import logger
from ..operations import repo as repo_interfaces
from . import xpak


def discern_loc(base, pkg, extension='.tbz2'):
    return pjoin(base, pkg.category, f"{pkg.package}-{pkg.fullver}{extension}")


_metadata_rewrites = {
    "CONTENTS": "contents",
    "source_repository": "repository",
    "fullslot": "SLOT",
}


def generate_attr_dict(pkg, portage_compatible=True):
    d = {}
    for k in pkg.tracked_attributes:
        if k == "contents":
            continue
        v = getattr(pkg, k)
        if k == 'environment':
            d['environment.bz2'] = compress_data(
                'bzip2', v.bytes_fileobj().read())
            continue
        elif not isinstance(v, str):
            try:
                s = ' '.join(v)
            except TypeError:
                s = str(v)
        else:
            s = v
        d[_metadata_rewrites.get(k, k.upper())] = s
    d[f"{pkg.package}-{pkg.fullver}.ebuild"] = pkg.ebuild.text_fileobj().read()

    # this shouldn't be necessary post portage 2.2.
    # till then, their code requires redundant data,
    # so we've got this.
    if portage_compatible:
        d["CATEGORY"] = pkg.category
        d["PF"] = pkg.PF
    return d


class install(repo_interfaces.install):

    @steal_docs(repo_interfaces.install)
    def add_data(self):
        if self.observer is None:
            end = start = lambda x: None
        else:
            start = self.observer.phase_start
            end = self.observer.phase_end
        pkg = self.new_pkg
        final_path = discern_loc(self.repo.base, pkg, self.repo.extension)
        tmp_path = pjoin(
            os.path.dirname(final_path),
            ".tmp.%i.%s" % (os.getpid(), os.path.basename(final_path)))

        self.tmp_path, self.final_path = tmp_path, final_path

        if not ensure_dirs(os.path.dirname(tmp_path), mode=0o755):
            raise repo_interfaces.Failure(
                f"failed creating directory: {os.path.dirname(tmp_path)!r}")
        try:
            start(f"generating tarball: {tmp_path}")
            tar.write_set(
                pkg.contents, tmp_path, compressor='bzip2',
                parallelize=True)
            end("tarball created", True)
            start("writing Xpak")
            # ok... got a tarball.  now add xpak.
            xpak.Xpak.write_xpak(tmp_path, generate_attr_dict(pkg))
            end("wrote Xpak", True)
            # ok... we tagged the xpak on.
            os.chmod(tmp_path, 0o644)
        except Exception as e:
            try:
                unlink_if_exists(tmp_path)
            except EnvironmentError as e:
                logger.warning(f"failed removing {tmp_path!r}: {e}")
            raise
        return True

    def finalize_data(self):
        os.rename(self.tmp_path, self.final_path)
        return True


class uninstall(repo_interfaces.uninstall):

    @steal_docs(repo_interfaces.uninstall)
    def remove_data(self):
        return True

    @steal_docs(repo_interfaces.uninstall)
    def finalize_data(self):
        os.unlink(discern_loc(self.repo.base, self.old_pkg, self.repo.extension))
        return True


class replace(install, uninstall, repo_interfaces.replace):

    @steal_docs(repo_interfaces.replace)
    def finalize_data(self):
        # we just invoke install finalize_data, since it atomically
        # transfers the new pkg in
        install.finalize_data(self)
        return True


class operations(repo_interfaces.operations):

    def _cmd_implementation_install(self, *args):
        return install(self.repo, *args)

    def _cmd_implementation_uninstall(self, *args):
        return uninstall(self.repo, *args)

    def _cmd_implementation_replace(self, *args):
        return replace(self.repo, *args)
