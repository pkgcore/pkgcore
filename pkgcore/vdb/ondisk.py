# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, stat, errno, shutil
from pkgcore.repository import prototype, errors

#needed to grab the PN
from pkgcore.ebuild.cpv import CPV as cpv
from pkgcore.fs.util import ensure_dirs
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.util.currying import pre_curry
from pkgcore.vdb.contents import ContentsFile
from pkgcore.plugins import get_plugin
from pkgcore.interfaces import repo as repo_interfaces
from pkgcore.interfaces import data_source
from pkgcore.util.osutils import listdir_dirs
from pkgcore.repository import multiplex, virtual
from pkgcore.util import bzip2

from pkgcore.util.demandload import demandload
demandload(globals(), "logging time tempfile "+
    "pkgcore.ebuild:conditionals "+
    "pkgcore.restrictions:boolean ")


class bz2_data_source(data_source.data_source):
    
    def __init__(self, location, mutable=False):
        self.location = location
        self.mutable = mutable
    
    def _get_data(self):
        return bzip2.decompress(open(self.location, "rb").read())
    
    def _set_data(self, data):
        open(self.location, "wb").write(bzip2.compress(data))
        return data
    
    data = property(_get_data, _set_data)
    
    
class tree(prototype.tree):
    livefs = True
    configured = False
    configurables = ("domain", "settings")
    configure = None
    format_magic = "ebuild_built"	

    def __init__(self, location):
        prototype.tree.__init__(self, frozen=False)
        self.base = self.location = location
        self._versions_tmp_cache = {}
        try:
            st = os.lstat(self.base)
            if not stat.S_ISDIR(st.st_mode):
                raise errors.InitializationError(
                    "base not a dir: %s" % self.base)
            elif not st.st_mode & (os.X_OK|os.R_OK):
                raise errors.InitializationError(
                    "base lacks read/executable: %s" % self.base)

        except OSError:
            raise errors.InitializationError(
                "lstat failed on base %s" % self.base)

        self.package_class = get_plugin("format", self.format_magic)(self)

    def _get_categories(self, *optionalCategory):
        # return if optionalCategory is passed... cause it's not yet supported
        if optionalCategory:
            return {}
        try:
            try:
                return tuple(listdir_dirs(self.base))
            except (OSError, IOError), e:
                raise KeyError("failed fetching categories: %s" % str(e))
        finally:
            pass

    def _get_packages(self, category):
        cpath = os.path.join(self.base, category.lstrip(os.path.sep))
        l = set()
        d = {}
        try:
            for x in listdir_dirs(cpath):
                if x.endswith(".lockfile") or x.startswith("-MERGING-"):
                    continue
                x = cpv(category+"/"+x)
                l.add(x.package)
                d.setdefault(category+"/"+x.package, []).append(x.fullver)
        except (OSError, IOError), e:
            raise KeyError("failed fetching packages for category %s: %s" % \
            (os.path.join(self.base, category.lstrip(os.path.sep)), str(e)))

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_ebuild_path(self, pkg):
        s = "%s-%s" % (pkg.package, pkg.fullver)
        return os.path.join(self.base, pkg.category, s, s+".ebuild")

    _metadata_rewrites = {
        "depends":"DEPEND", "rdepends":"RDEPEND", "post_rdepends":"PDEPEND",
        "use":"USE", "eapi":"EAPI", "CONTENTS":"contents"}

    def _get_metadata(self, pkg):
        return IndeterminantDict(pre_curry(self._internal_load_key,
                                           os.path.dirname(pkg.path)))

    def _internal_load_key(self, path, key):
        key = self._metadata_rewrites.get(key, key)
        if key == "contents":
            data = ContentsFile(os.path.join(path, "CONTENTS"))
        elif key == "environment":
            fp = os.path.join(path, key)
            if not os.path.exists(fp+".bz2"):
                if not os.path.exists(fp):
                    # icky.
                    raise KeyError("environment: no environment file found")
                data = data_source.local_source(fp)
            else:
                data = bz2_data_source(fp+".bz2")
        else:
            try:
                data = open(os.path.join(path, key), "r", 32384).read().strip()
            except (OSError, IOError):
                data = ""
        return data

    def notify_remove_package(self, pkg):
        remove_it = len(self.packages[pkg.category]) == 1
        prototype.tree.notify_remove_package(self, pkg)
        if remove_it:
            try:
                os.rmdir(os.path.join(self.base, pkg.category))
            except OSError, oe:
                if oe.errno != errno.ENOTEMPTY:
                    raise
                # silently swallow it;
                del oe


class ConfiguredTree(multiplex.tree):

    livefs = True

    def __init__(self, raw_vdb, domain, domain_settings):
        self.domain = domain
        self.domain_settings = domain_settings
        self.raw_vdb = raw_vdb
        self.raw_virtual = virtual.tree(self._grab_virtuals, livefs=True)
        multiplex.tree.__init__(self, raw_vdb, self.raw_virtual)
        self.frozen = raw_vdb.frozen

    def _install(self, pkg, *a, **kw):
        # need to verify it's not in already...
        return install(self.domain_settings, self.raw_vdb, pkg, *a, **kw)

    def _uninstall(self, pkg, *a, **kw):
        return uninstall(self.domain_settings, self.raw_vdb, pkg, *a, **kw)

    def _replace(self, oldpkg, newpkg, *a, **kw):
        return replace(
            self.domain_settings, self.raw_vdb, oldpkg, newpkg, *a, **kw)

    def _grab_virtuals(self):
        virtuals = {}
        for pkg in self.raw_vdb:
            for virtual in pkg.provides.evaluate_depset(pkg.use):
                virtuals.setdefault(virtual.package, {}).setdefault(
                    pkg.fullver, []).append(pkg)

        for pkg_dict in virtuals.itervalues():
            for full_ver, rdep_atoms in pkg_dict.iteritems():
                if len(rdep_atoms) == 1:
                    pkg_dict[full_ver] = rdep_atoms[0].unversioned_atom
                else:
                    pkg_dict[full_ver] = OrRestriction(
                        finalize=True,
                        *[x.unversioned_atom for x in rdep_atoms])
        return virtuals

tree.configure = ConfiguredTree

def _get_ebuild_op_args_kwds(self):
    return (dict(self.domain_settings),), {}

class install(repo_interfaces.install):

    def __init__(self, domain_settings, repo, pkg, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.install.__init__(self, repo, pkg, *a, **kw)

    _get_format_op_args_kwds = _get_ebuild_op_args_kwds

    def merge_metadata(self, dirpath=None):
        # error checking?
        if dirpath is None:
            dirpath = self.dirpath
        ensure_dirs(dirpath)
        rewrite = self.repo._metadata_rewrites
        for k in self.pkg.tracked_attributes:
            if k == "contents":
                v = ContentsFile(os.path.join(dirpath, "CONTENTS"),
                                 mutable=True, create=True)
                for x in self.me.csets["install"]:
                    # $10 this ain't right.  verify this- harring
                    if self.offset:
                        v.add(x.change_attributes(
                                location=os.path.join(self.offset, x.location)))
                    else:
                        v.add(x)
                v.flush()
            elif k == "environment":
                data = bzip2.compress(self.pkg.environment.get_fileobj().read())
                open(os.path.join(dirpath, "environment.bz2"), "w").write(data)
                del data
            elif isinstance(k, boolean.base):
                if isinstance(k, conditionals.DepSet):
                    s = str(k)
                else:
                    s = conditionals.stringify_boolean(k)
            else:
                v = getattr(self.pkg, k)
                if not isinstance(v, basestring):
                    try:
                        s = ' '.join(v)
                    except TypeError:
                        s = str(v)
                else:
                    s = v
                if not s.endswith("\n"):
                    s += "\n"
                open(os.path.join(
                        dirpath,
                        rewrite.get(k, k.upper())), "w", 32384).write(s)

        # ebuild_data is the actual ebuild- no point in holding onto
        # it for built ebuilds, but if it's there, we store it.
        o = getattr(self.pkg, "raw_ebuild", None)
        if o is None:
            logging.warn(
                "doing install/replace op, "
                "but source package doesn't provide the actual ebuild data.  "
                "Creating an empty file")
            o = ''
        # XXX lil hackish accessing PF
        open(os.path.join(dirpath, self.pkg.PF + ".ebuild"), "w").write(o)

        # XXX finally, hack to keep portage from doing stupid shit.
        # relies on counter to discern what to punt during
        # merging/removal, we don't need that crutch however. problem?
        # No counter file, portage wipes all of our merges (friendly
        # bugger).
        # need to get zmedico to localize the counter
        # creation/counting to per CP for this trick to behave
        # perfectly.
        open(os.path.join(dirpath, "COUNTER"), "w").write(str(int(time.time())))
        return True


class uninstall(repo_interfaces.uninstall):

    def __init__(self, domain_settings, repo, pkg, offset=None, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.uninstall.__init__(
            self, repo, pkg, offset=offset, *a, **kw)

    _get_format_op_args_kwds = _get_ebuild_op_args_kwds

    def unmerge_metadata(self, dirpath=None):
        if dirpath is None:
            dirpath = self.dirpath
        shutil.rmtree(self.dirpath)
        return True

# should convert these to mixins.
class replace(install, uninstall, repo_interfaces.replace):

    def __init__(self, domain_settings, repo, pkg, newpkg, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.newpath = os.path.join(
            repo.base, newpkg.category, newpkg.package+"-"+newpkg.fullver)
        self.tmpdirpath = os.path.join(
            os.path.dirname(self.dirpath),
            ".tmp."+os.path.basename(self.dirpath))
        self.domain_settings = domain_settings
        repo_interfaces.replace.__init__(self, repo, pkg, newpkg, *a, **kw)

    _get_format_op_args_kwds = _get_ebuild_op_args_kwds

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
