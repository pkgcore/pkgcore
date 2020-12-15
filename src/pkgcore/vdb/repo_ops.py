__all__ = ("install", "uninstall", "replace", "operations")

import os
import shutil
import time
from itertools import chain

from snakeoil import compression
from snakeoil.data_source import local_source
from snakeoil.osutils import ensure_dirs, normpath, pjoin
from snakeoil.version import get_version

from .. import __title__
from ..ebuild import conditionals
from ..log import logger
from ..operations import repo as repo_ops
from .contents import ContentsFile


def update_mtime(path, timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    logger.debug(f"updating vdb timestamp for {path!r}")
    try:
        os.utime(path, (timestamp, timestamp))
    except EnvironmentError as e:
        logger.error(f"failed updated vdb timestamp for {path!r}: {e}")


class install(repo_ops.install):

    def __init__(self, repo, newpkg, observer):
        base = pjoin(repo.location, newpkg.category)
        dirname = f"{newpkg.package}-{newpkg.fullver}"
        self.install_path = pjoin(base, dirname)
        self.tmp_write_path = pjoin(base, f".tmp.{dirname}")
        super().__init__(repo, newpkg, observer)

    def add_data(self, domain):
        # error checking?
        dirpath = self.tmp_write_path
        ensure_dirs(dirpath, mode=0o755, minimal=True)
        update_mtime(self.repo.location)
        rewrite = self.repo._metadata_rewrites
        for k in self.new_pkg.tracked_attributes:
            if k == "contents":
                v = ContentsFile(pjoin(dirpath, "CONTENTS"),
                                 mutable=True, create=True)
                v.update(self.new_pkg.contents)
                v.flush()
            elif k == "environment":
                data = compression.compress_data('bzip2',
                    self.new_pkg.environment.bytes_fileobj().read())
                with open(pjoin(dirpath, "environment.bz2"), "wb") as f:
                    f.write(data)
                del data
            else:
                v = getattr(self.new_pkg, k)
                if k in ('bdepend', 'depend', 'rdepend'):
                    s = v.slotdep_str(domain)
                elif k == 'user_patches':
                    s = '\n'.join(chain.from_iterable(files for _, files in v))
                elif not isinstance(v, str):
                    try:
                        s = ' '.join(v)
                    except TypeError:
                        s = str(v)
                else:
                    s = v
                with open(pjoin(dirpath, rewrite.get(k, k.upper())), "w", 32768) as f:
                    if s:
                        s += '\n'
                    f.write(s)

        # ebuild_data is the actual ebuild- no point in holding onto
        # it for built ebuilds, but if it's there, we store it.
        o = getattr(self.new_pkg, "ebuild", None)
        if o is None:
            logger.warning(
                "doing install/replace op, "
                "but source package doesn't provide the actual ebuild data.  "
                "Creating an empty file")
            o = ''
        else:
            o = o.bytes_fileobj().read()
        # XXX lil hackish accessing PF
        with open(pjoin(dirpath, self.new_pkg.PF + ".ebuild"), "wb") as f:
            f.write(o)

        # install NEEDED and NEEDED.ELF.2 files from tmpdir if they exist
        pkg_tmpdir = normpath(pjoin(domain.pm_tmpdir, self.new_pkg.category,
                                    self.new_pkg.PF, 'temp'))
        for f in ['NEEDED', 'NEEDED.ELF.2']:
            fp = pjoin(pkg_tmpdir, f)
            if os.path.exists(fp):
                local_source(fp).transfer_to_path(pjoin(dirpath, f))

        # XXX finally, hack to keep portage from doing stupid shit.
        # relies on counter to discern what to punt during
        # merging/removal, we don't need that crutch however. problem?
        # No counter file, portage wipes all of our merges (friendly
        # bugger).
        # need to get zmedico to localize the counter
        # creation/counting to per CP for this trick to behave
        # perfectly.
        with open(pjoin(dirpath, "COUNTER"), "w") as f:
            f.write(str(int(time.time())))

        # finally, we mark who made this.
        with open(pjoin(dirpath, "PKGMANAGER"), "w") as f:
            f.write(get_version(__title__, __file__))
        return True

    def finalize_data(self):
        os.rename(self.tmp_write_path, self.install_path)
        update_mtime(self.repo.location)
        return True


class uninstall(repo_ops.uninstall):

    def __init__(self, repo, pkg, observer):
        self.remove_path = pjoin(
            repo.location, pkg.category, pkg.package+"-"+pkg.fullver)
        super().__init__(repo, pkg, observer)

    def remove_data(self):
        return True

    def finalize_data(self):
        update_mtime(self.repo.location)
        shutil.rmtree(self.remove_path)
        update_mtime(self.repo.location)
        return True


# should convert these to mixins.
class replace(repo_ops.replace, install, uninstall):

    def __init__(self, repo, pkg, newpkg, observer):
        uninstall.__init__(self, repo, pkg, observer)
        install.__init__(self, repo, newpkg, observer)

    remove_data = uninstall.remove_data

    def add_data(self, domain):
        return install.add_data(self, domain)

    def finalize_data(self):
        # XXX: should really restructure this into
        # a rename of the unmerge dir, rename merge into it's place (for
        # literal same fullver replacements), then wipe the unmerge
        # that minimizes the window for races, and gets the data in place
        # should unmerge somehow die.
        uninstall.finalize_data(self)
        install.finalize_data(self)
        return True


class operations(repo_ops.operations):

    def _cmd_implementation_install(self, pkg, observer):
        return install(self.repo, pkg, observer)

    def _cmd_implementation_uninstall(self, pkg, observer):
        return uninstall(self.repo, pkg, observer)

    def _cmd_implementation_replace(self, oldpkg, newpkg, observer):
        return replace(self.repo, oldpkg, newpkg, observer)

    def _cmd_api_regen_cache(self, *args, **kwargs):
        # disable threaded cache updates
        super()._cmd_api_regen_cache(*args, threads=1, **kwargs)
