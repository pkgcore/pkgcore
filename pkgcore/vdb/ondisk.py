# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os, stat, errno

from pkgcore.repository import prototype, errors
from pkgcore.vdb import virtuals
from pkgcore.plugin import get_plugin
from pkgcore.interfaces import data_source
from pkgcore.repository import multiplex
from pkgcore.config import ConfigHint
#needed to grab the PN
from pkgcore.ebuild.cpv import versioned_CPV
from pkgcore.ebuild.errors import InvalidCPV

from snakeoil.osutils import pjoin
from snakeoil.mappings import IndeterminantDict
from snakeoil.currying import partial
from snakeoil.osutils import listdir_dirs, readfile
from pkgcore.util import bzip2
from snakeoil.demandload import demandload
demandload(globals(),
    'pkgcore.vdb:repo_ops',
    'pkgcore.vdb.contents:ContentsFile',
    'pkgcore.log:logger',
)


class bz2_data_source(data_source.base):

    def __init__(self, location, mutable=False):
        data_source.base.__init__(self)
        self.location = location
        self.mutable = mutable

    def get_fileobj(self):
        data = bzip2.decompress(readfile(self.location))
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

    pkgcore_config_type = ConfigHint({'location': 'str',
        'cache_location': 'str', 'repo_id':'str',
        'disable_cache': 'bool'}, typename='repo')

    def __init__(self, location, cache_location=None, repo_id='vdb',
        disable_cache=False):
        prototype.tree.__init__(self, frozen=False)
        self.repo_id = repo_id
        self.base = self.location = location
        if disable_cache:
            cache_location = None
        elif cache_location is None:
            cache_location = pjoin("/var/cache/edb/dep",
                location.lstrip("/"))
        self.cache_location = cache_location
        self._versions_tmp_cache = {}
        try:
            st = os.stat(self.base)
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
                return tuple(x for x in listdir_dirs(self.base) if not
                             x.startswith('.'))
            except (OSError, IOError), e:
                raise KeyError("failed fetching categories: %s" % str(e))
        finally:
            pass

    def _get_packages(self, category):
        cpath = pjoin(self.base, category.lstrip(os.path.sep))
        l = set()
        d = {}
        bad = False
        try:
            for x in listdir_dirs(cpath):
                if x.startswith(".tmp.") or x.endswith(".lockfile") \
                    or x.startswith("-MERGING-"):
                    continue
                try:
                    pkg = versioned_CPV(category+"/"+x)
                except InvalidCPV:
                    bad = True
                if bad or not pkg.fullver:
                    if '-scm' in x:
                        bad = 'scm'
                    elif '-try' in x:
                        bad = 'try'
                    else:
                        raise InvalidCPV("%s/%s: no version component" %
                            (category, x))
                    logger.error("merged -%s pkg detected: %s/%s. "
                        "throwing exception due to -%s not being a valid"
                        " version component.  Silently ignoring that "
                        "specific version is not viable either since it "
                        "would result in pkgcore stomping whatever it was "
                        "that -%s version merged.  "
                        "This is why embrace and extend is bad, mm'kay.  "
                        "Use the offending pkg manager that merged it to "
                        "unmerge it." % (bad, category, x, bad, bad))
                    raise InvalidCPV("%s/%s: -%s version component is "
                        "not standard." % (category, x, bad))
                l.add(pkg.package)
                d.setdefault((category, pkg.package), []).append(pkg.fullver)
        except (OSError, IOError), e:
            raise KeyError("failed fetching packages for category %s: %s" % \
            (pjoin(self.base, category.lstrip(os.path.sep)), str(e)))

        self._versions_tmp_cache.update(d)
        return tuple(l)

    def _get_versions(self, catpkg):
        return tuple(self._versions_tmp_cache.pop(catpkg))

    def _get_ebuild_path(self, pkg):
        s = "%s-%s" % (pkg.package, pkg.fullver)
        return pjoin(self.base, pkg.category, s, s+".ebuild")

    _metadata_rewrites = {
        "depends":"DEPEND", "rdepends":"RDEPEND", "post_rdepends":"PDEPEND",
        "use":"USE", "eapi":"EAPI", "CONTENTS":"contents", "provides":"PROVIDE"}

    def _get_metadata(self, pkg):
        return IndeterminantDict(partial(self._internal_load_key,
            pjoin(self.base, pkg.category,
                "%s-%s" % (pkg.package, pkg.fullver))))

    def _internal_load_key(self, path, key):
        key = self._metadata_rewrites.get(key, key)
        if key == "contents":
            data = ContentsFile(pjoin(path, "CONTENTS"), mutable=True)
        elif key == "environment":
            fp = pjoin(path, key)
            if not os.path.exists(fp+".bz2"):
                if not os.path.exists(fp):
                    # icky.
                    raise KeyError("environment: no environment file found")
                data = data_source.local_source(fp)
            else:
                data = bz2_data_source(fp+".bz2")
        elif key == "ebuild":
            fp = pjoin(path,
                os.path.basename(path.rstrip(os.path.sep))+".ebuild")
            data = data_source.local_source(fp)
        elif key == 'repository':
            # try both, for portage/paludis compatibility.
            data = readfile(pjoin(path, key), True)
            if data is None:
                data = readfile(pjoin(path, key.upper()), True)
                if data is None:
                    raise KeyError(key)
        else:
            data = readfile(pjoin(path, key), True)
            if data is None:
                raise KeyError((path, key))
        return data

    def notify_remove_package(self, pkg):
        remove_it = len(self.packages[pkg.category]) == 1
        prototype.tree.notify_remove_package(self, pkg)
        if remove_it:
            try:
                os.rmdir(pjoin(self.base, pkg.category))
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
    frozen_settable = False

    def __init__(self, raw_vdb, domain, domain_settings):
        self.domain = domain
        self.domain_settings = domain_settings
        self.raw_vdb = raw_vdb
        if raw_vdb.cache_location is not None:
            self.old_style_virtuals = virtuals.caching_virtuals(raw_vdb,
                raw_vdb.cache_location)
        else:
            self.old_style_virtuals = virtuals.non_caching_virtuals(raw_vdb)
        multiplex.tree.__init__(self, raw_vdb, self.old_style_virtuals)

    @property
    def frozen(self):
        return self.raw_vdb.frozen

    def _install(self, pkg, *a, **kw):
        # need to verify it's not in already...
        kw['offset'] = self.domain.root
        kw.setdefault('triggers', []).extend(self.domain.get_extra_triggers())
        return repo_ops.install(self.domain_settings, self.raw_vdb, pkg, *a, **kw)

    def _uninstall(self, pkg, *a, **kw):
        kw['offset'] = self.domain.root
        kw.setdefault('triggers', []).extend(self.domain.get_extra_triggers())
        return repo_ops.uninstall(self.domain_settings, self.raw_vdb, pkg, *a, **kw)

    def _replace(self, oldpkg, newpkg, *a, **kw):
        kw['offset'] = self.domain.root
        kw.setdefault('triggers', []).extend(self.domain.get_extra_triggers())
        return repo_ops.replace(
            self.domain_settings, self.raw_vdb, oldpkg, newpkg, *a, **kw)


tree.configure = ConfiguredTree
