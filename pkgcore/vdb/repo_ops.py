# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os, shutil

from pkgcore.interfaces import repo as repo_interfaces
#needed to grab the PN

from pkgcore.const import VERSION

from snakeoil.osutils import ensure_dirs, pjoin
from pkgcore.util import bzip2
from snakeoil.demandload import demandload
demandload(globals(),
    'time',
    'pkgcore.ebuild:conditionals',
    'pkgcore.ebuild:triggers',
    'pkgcore.log:logger',
    'pkgcore.fs.ops:change_offset_rewriter',
    'pkgcore.vdb.contents:ContentsFile',
)


def _get_default_ebuild_op_args_kwds(self):
    return (dict(self.domain_settings),), {}

def _default_customize_engine(op_inst, engine):
    triggers.customize_engine(op_inst.domain_settings, engine)


class install(repo_interfaces.livefs_install):

    def __init__(self, domain_settings, repo, pkg, *args):
        self.dirpath = pjoin(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.livefs_install.__init__(self, repo, pkg, *args)

    install_get_format_op_args_kwds = _get_default_ebuild_op_args_kwds
    customize_engine = _default_customize_engine

    def merge_metadata(self, dirpath=None):
        # error checking?
        if dirpath is None:
            dirpath = self.dirpath
        ensure_dirs(dirpath, mode=0755, minimal=True)
        rewrite = self.repo._metadata_rewrites
        for k in self.new_pkg.tracked_attributes:
            if k == "contents":
                v = ContentsFile(pjoin(dirpath, "CONTENTS"),
                                 mutable=True, create=True)
                # strip the offset.
                if self.offset not in (None, '/'):
                    v.update(change_offset_rewriter(self.offset, '/',
                        self.me.csets["install"]))
                else:
                    v.update(self.me.csets["install"])
                v.flush()
            elif k == "environment":
                data = bzip2.compress(
                    self.new_pkg.environment.get_fileobj().read())
                open(pjoin(dirpath, "environment.bz2"), "w").write(data)
                del data
            else:
                v = getattr(self.new_pkg, k)
                if k == 'provides':
                    versionless_providers = lambda b:b.key
                    s = conditionals.stringify_boolean(v,
                        func=versionless_providers)
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
            logger.warn(
                "doing install/replace op, "
                "but source package doesn't provide the actual ebuild data.  "
                "Creating an empty file")
            o = ''
        else:
            o = o.get_fileobj().read()
        # XXX lil hackish accessing PF
        open(pjoin(dirpath, self.new_pkg.PF + ".ebuild"), "w").write(o)

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


class uninstall(repo_interfaces.livefs_uninstall):

    def __init__(self, domain_settings, repo, pkg, *args):
        self.dirpath = pjoin(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.livefs_uninstall.__init__(
            self, repo, pkg, *args)

    uninstall_get_format_op_args_kwds = _get_default_ebuild_op_args_kwds
    customize_engine = _default_customize_engine

    def unmerge_metadata(self, dirpath=None):
        if dirpath is None:
            dirpath = self.dirpath
        shutil.rmtree(self.dirpath)
        return True


# should convert these to mixins.
class replace(repo_interfaces.livefs_replace, install, uninstall):

    def __init__(self, domain_settings, repo, pkg, newpkg, *a):
        self.dirpath = pjoin(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.newpath = pjoin(
            repo.base, newpkg.category, newpkg.package+"-"+newpkg.fullver)
        self.tmpdirpath = pjoin(
            os.path.dirname(self.dirpath),
            ".tmp."+os.path.basename(self.dirpath))
        self.domain_settings = domain_settings
        repo_interfaces.livefs_replace.__init__(self, repo, pkg, newpkg, *a)

    _get_format_op_args_kwds = _get_default_ebuild_op_args_kwds
    customize_engine = _default_customize_engine

    def merge_metadata(self, *a, **kw):
        kw["dirpath"] = self.tmpdirpath
        if os.path.exists(self.tmpdirpath):
            shutil.rmtree(self.tmpdirpath)
        return install.merge_metadata(self, *a, **kw)

    def unmerge_metadata(self, *a, **kw):
        ret = uninstall.unmerge_metadata(self, *a, **kw)
        if not ret:
            return ret
        os.rename(self.tmpdirpath, self.newpath)
        return True


class operations(repo_interfaces.operations):

    def _add_triggers(self, existing_triggers):
        if existing_triggers is None:
            existing_triggers = []
        existing_triggers.extend(self.repo.domain.get_extra_triggers())
        return existing_triggers

    def _cmd_install(self, pkg, observer, triggers=None):
        return install(self.repo.domain_settings, self.repo.raw_vdb, pkg,
            observer,
            self._add_triggers(triggers),
            self.repo.domain.root)

    def _cmd_uninstall(self, pkg, observer, triggers=None):
        return uninstall(self.repo.domain_settings, self.repo.raw_vdb, pkg,
            observer,
            self._add_triggers(triggers),
            self.repo.domain.root)

    def _cmd_replace(self, oldpkg, newpkg, observer, triggers=None):
        return replace(self.repo.domain_settings, self.repo.raw_vdb,
            oldpkg, newpkg, observer,
            self._add_triggers(triggers),
            self.repo.domain.root)
