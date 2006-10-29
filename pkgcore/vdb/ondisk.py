# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, stat, errno, shutil
from pkgcore.repository import prototype, errors

#needed to grab the PN
from pkgcore.ebuild.cpv import CPV as cpv
from pkgcore.util.osutils import ensure_dirs
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.util.currying import partial
from pkgcore.vdb.contents import ContentsFile
from pkgcore.plugin import get_plugin
from pkgcore.interfaces import repo as repo_interfaces
from pkgcore.interfaces import data_source
from pkgcore.util.osutils import listdir_dirs
from pkgcore.repository import multiplex, virtual
from pkgcore.util import bzip2
from pkgcore.util.lists import iflatten_instance
from pkgcore.config import ConfigHint

from pkgcore.util.demandload import demandload
demandload(globals(),
           "logging time "
           "pkgcore.ebuild:conditionals "
           "pkgcore.restrictions:boolean,packages "
           "pkgcore.const "
           "pkgcore.ebuild:triggers "
    )


class bz2_data_source(data_source.base):

    def __init__(self, location, mutable=False):
        data_source.base.__init__(self)
        self.location = location
        self.mutable = mutable

    def get_fileobj(self):
        data = bzip2.decompress(open(self.location, 'rb').read())
        if self.mutable:
            return data_source.write_StringIO(self._set_data, data)
        return data_source.read_StringIO(data)

    def _set_data(self, data):
        open(self.location, "wb").write(bzip2.compress(data))


class tree(prototype.tree):
    livefs = True
    configured = False
    configurables = ("domain", "settings")
    configure = None
    format_magic = "ebuild_built"

    pkgcore_config_type = ConfigHint({'location': 'str'}, typename='repo')

    def __init__(self, location):
        prototype.tree.__init__(self, frozen=False)
        self.base = self.location = location
        self._versions_tmp_cache = {}
        try:
            st = os.lstat(self.base)
            if not stat.S_ISDIR(st.st_mode):
                raise errors.InitializationError(
                    "base not a dir: %r" % self.base)
            elif not st.st_mode & (os.X_OK|os.R_OK):
                raise errors.InitializationError(
                    "base lacks read/executable: %r" % self.base)

        except OSError:
            raise errors.InitializationError(
                "lstat failed on base %r" % self.base)

        self.package_class = get_plugin('format.' + self.format_magic)(self)

    def _get_categories(self, *optional_category):
        # return if optional_category is passed... cause it's not yet supported
        if optional_category:
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
                if x.startswith(".tmp.") or x.endswith(".lockfile") \
                    or x.startswith("-MERGING-"):
                    continue
                x = cpv(category+"/"+x)
                l.add(x.package)
                d.setdefault((category, x.package), []).append(x.fullver)
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
        "use":"USE", "eapi":"EAPI", "CONTENTS":"contents", "provides":"PROVIDE"}

    def _get_metadata(self, pkg):
        return IndeterminantDict(partial(self._internal_load_key,
            os.path.join(self.base, pkg.category,
                "%s-%s" % (pkg.package, pkg.fullver))))

    def _internal_load_key(self, path, key):
        key = self._metadata_rewrites.get(key, key)
        if key == "contents":
            data = ContentsFile(os.path.join(path, "CONTENTS"), mutable=True)
        elif key == "environment":
            fp = os.path.join(path, key)
            if not os.path.exists(fp+".bz2"):
                if not os.path.exists(fp):
                    # icky.
                    raise KeyError("environment: no environment file found")
                data = data_source.local_source(fp)
            else:
                data = bz2_data_source(fp+".bz2")
        elif key == "ebuild":
            fp = os.path.join(os.path.dirname(path), 
                os.path.basename(path.rstrip(os.path.sep))+".ebuild")
            data = data_source.local_source(fp)
        else:
            try:
                data = open(os.path.join(path, key), "r").read().strip()
            except (OSError, IOError):
                raise KeyError(key)
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

    def __str__(self):
        return '%s.%s: location %s' % (
            self.__class__.__module__, self.__class__.__name__, self.base)


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
            for virtualpkg in iflatten_instance(pkg.provides.evaluate_depset(pkg.use)):
                virtuals.setdefault(virtualpkg.package, {}).setdefault(
                    pkg.fullver, []).append(pkg)

        for pkg_dict in virtuals.itervalues():
            for full_ver, rdep_atoms in pkg_dict.iteritems():
                if len(rdep_atoms) == 1:
                    pkg_dict[full_ver] = rdep_atoms[0].unversioned_atom
                else:
                    pkg_dict[full_ver] = packages.OrRestriction(
                        finalize=True,
                        *[x.unversioned_atom for x in rdep_atoms])
        return virtuals

tree.configure = ConfiguredTree

def _get_default_ebuild_op_args_kwds(self):
    return (dict(self.domain_settings),), {}

def _default_customize_engine(op_inst, engine):
    triggers.customize_engine(op_inst.domain_settings, engine)

class install(repo_interfaces.livefs_install):

    def __init__(self, domain_settings, repo, pkg, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.livefs_install.__init__(self, repo, pkg, *a, **kw)

    install_get_format_op_args_kwds = _get_default_ebuild_op_args_kwds
    customize_engine = _default_customize_engine

    def merge_metadata(self, dirpath=None):
        # error checking?
        if dirpath is None:
            dirpath = self.dirpath
        ensure_dirs(dirpath)
        rewrite = self.repo._metadata_rewrites
        for k in self.new_pkg.tracked_attributes:
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
                data = bzip2.compress(
                    self.new_pkg.environment.get_fileobj().read())
                open(os.path.join(dirpath, "environment.bz2"), "w").write(data)
                del data
            else:
                v = getattr(self.new_pkg, k)
                if k == 'provides':
                    def versionless_providers(b):
                        return b.key
                    v = getattr(self.new_pkg, k).restrictions
                    s = ' '.join(conditionals.stringify_boolean(x, 
                        func=versionless_providers)
                        for x in v)
                elif not isinstance(v, basestring):
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
                        rewrite.get(k, k.upper())), "w", 32768).write(s)

        # ebuild_data is the actual ebuild- no point in holding onto
        # it for built ebuilds, but if it's there, we store it.
        o = getattr(self.new_pkg, "ebuild", None)
        if o is None:
            logging.warn(
                "doing install/replace op, "
                "but source package doesn't provide the actual ebuild data.  "
                "Creating an empty file")
            o = ''
        else:
            o = o.get_fileobj().read()
        # XXX lil hackish accessing PF
        open(os.path.join(dirpath, self.new_pkg.PF + ".ebuild"), "w").write(o)

        # XXX finally, hack to keep portage from doing stupid shit.
        # relies on counter to discern what to punt during
        # merging/removal, we don't need that crutch however. problem?
        # No counter file, portage wipes all of our merges (friendly
        # bugger).
        # need to get zmedico to localize the counter
        # creation/counting to per CP for this trick to behave
        # perfectly.
        open(os.path.join(dirpath, "COUNTER"), "w").write(str(int(time.time())))
        
        #finally, we mark who made this.
        open(os.path.join(dirpath, "PKGMANAGER"), "w").write(
            "pkgcore-%s" % pkgcore.const.VERSION)
        return True


class uninstall(repo_interfaces.livefs_uninstall):

    def __init__(self, domain_settings, repo, pkg, offset=None, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.domain_settings = domain_settings
        repo_interfaces.livefs_uninstall.__init__(
            self, repo, pkg, offset=offset, *a, **kw)

    uninstall_get_format_op_args_kwds = _get_default_ebuild_op_args_kwds
    customize_engine = _default_customize_engine

    def unmerge_metadata(self, dirpath=None):
        if dirpath is None:
            dirpath = self.dirpath
        shutil.rmtree(self.dirpath)
        return True


# should convert these to mixins.
class replace(install, uninstall, repo_interfaces.livefs_replace):

    def __init__(self, domain_settings, repo, pkg, newpkg, *a, **kw):
        self.dirpath = os.path.join(
            repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
        self.newpath = os.path.join(
            repo.base, newpkg.category, newpkg.package+"-"+newpkg.fullver)
        self.tmpdirpath = os.path.join(
            os.path.dirname(self.dirpath),
            ".tmp."+os.path.basename(self.dirpath))
        self.domain_settings = domain_settings
        repo_interfaces.livefs_replace.__init__(self, repo, pkg, newpkg, *a, **kw)

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
