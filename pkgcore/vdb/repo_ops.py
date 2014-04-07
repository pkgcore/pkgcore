# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("install", "uninstall", "replace", "operations")

import os, shutil

from pkgcore.operations import repo as repo_ops

from pkgcore.const import VERSION

from snakeoil.osutils import ensure_dirs, pjoin, normpath
from snakeoil.demandload import demandload
from snakeoil import compression
demandload(globals(),
    'time',
    'pkgcore.ebuild:conditionals',
    'pkgcore.log:logger',
    'pkgcore.vdb.contents:ContentsFile',
    'snakeoil.data_source:local_source',
)


def update_mtime(path, timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    logger.debug("updating vdb timestamp for %r", path)
    try:
        os.utime(path, (timestamp, timestamp))
    except EnvironmentError, e:
        logger.error("failed updated vdb timestamp for %r: %s", path, e)


class install(repo_ops.install):

    def __init__(self, repo, newpkg, observer):
        base = pjoin(repo.location, newpkg.category)
        dirname = "%s-%s" % (newpkg.package, newpkg.fullver)
        self.install_path = pjoin(base, dirname)
        self.tmp_write_path = pjoin(base, '.tmp.%s' % (dirname,))
        repo_ops.install.__init__(self, repo, newpkg, observer)

    def add_data(self, domain):
        # error checking?
        dirpath = self.tmp_write_path
        ensure_dirs(dirpath, mode=0755, minimal=True)
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
                open(pjoin(dirpath, "environment.bz2"), "wb").write(data)
                del data
            else:
                v = getattr(self.new_pkg, k)
                if k == 'provides':
                    versionless_providers = lambda b:b.key
                    s = conditionals.stringify_boolean(v,
                        func=versionless_providers)
                elif k == 'eapi_obj':
                    # hackity hack.
                    s = v.magic
                    k = 'eapi'
                elif k == 'depends' or k == 'rdepends':
                    s = v.slotdep_str(domain)
                elif not isinstance(v, basestring):
                    try:
                        s = ' '.join(v)
                    except TypeError:
                        s = str(v)
                else:
                    s = v
                open(pjoin(
                        dirpath,
                        rewrite.get(k, k.upper())), "w", 32768).write(s)

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
        open(pjoin(dirpath, self.new_pkg.PF + ".ebuild"), "wb").write(o)

        # install NEEDED and NEEDED.ELF.2 files from tmpdir if they exist
        pkg_tmpdir = normpath(pjoin(domain._get_tempspace(), self.new_pkg.category,
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
        open(pjoin(dirpath, "COUNTER"), "w").write(str(int(time.time())))

        #finally, we mark who made this.
        open(pjoin(dirpath, "PKGMANAGER"), "w").write(
            "pkgcore-%s\n" % VERSION)
        return True

    def finalize_data(self):
        os.rename(self.tmp_write_path, self.install_path)
        update_mtime(self.repo.location)
        return True


class uninstall(repo_ops.uninstall):

    def __init__(self, repo, pkg, observer):
        self.remove_path = pjoin(
            repo.location, pkg.category, pkg.package+"-"+pkg.fullver)
        repo_ops.uninstall.__init__(self, repo, pkg, observer)

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

    _regen_disable_threads = True

    def _cmd_implementation_install(self, pkg, observer):
        return install(self.repo, pkg, observer)

    def _cmd_implementation_uninstall(self, pkg, observer):
        return uninstall(self.repo, pkg, observer)

    def _cmd_implementation_replace(self, oldpkg, newpkg, observer):
        return replace(self.repo, oldpkg, newpkg, observer)
