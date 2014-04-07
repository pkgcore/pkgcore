# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from __future__ import with_statement

"""
package class for buildable ebuilds
"""

__all__ = ("base", "package", "package_factory", "virtual_ebuild")

import os
from itertools import imap, chain

from pkgcore.package import metadata
from pkgcore.package import errors as metadata_errors
from pkgcore.ebuild.cpv import CPV
from pkgcore.ebuild import conditionals
from pkgcore.ebuild.atom import atom
from pkgcore.cache import errors as cache_errors
from pkgcore.restrictions.packages import AndRestriction
from pkgcore.restrictions import boolean, values
from pkgcore.package.errors import MissingChksum
from pkgcore.fetch.errors import UnknownMirror
from pkgcore.fetch import fetchable, mirror, uri_list, default_mirror
from pkgcore.ebuild import processor

from snakeoil.mappings import IndeterminantDict
from snakeoil.currying import partial
from snakeoil import klass
from snakeoil.compatibility import intern

from snakeoil import demandload
demandload.demandload(globals(),
    "pkgcore.log:logger",
    "pkgcore.ebuild.eapi:get_eapi",
    "snakeoil:data_source,fileutils",
    "snakeoil:chksum",
)

demandload.demand_compile_regexp(globals(),
    '_parse_EAPI_RE',
    r"^EAPI=(['\"]?)([A-Za-z0-9+_.-]*)\1[\t ]*(?:#.*)?")


def generate_depset(c, key, non_package_type, s, **kwds):
    if non_package_type:
        return conditionals.DepSet.parse(s.data.pop(key, ""), c,
            operators={"||":boolean.OrRestriction,
            "":boolean.AndRestriction}, **kwds)
    eapi_obj = s.eapi_obj
    if not eapi_obj.is_supported:
        raise metadata_errors.MetadataException(s, "eapi", "unsupported eapi: %s" % eapi_obj.magic)
    kwds['element_func'] = eapi_obj.atom_kls
    kwds['transitive_use_atoms'] = eapi_obj.options.transitive_use_atoms
    return conditionals.DepSet.parse(s.data.pop(key, ""), c, **kwds)

def _mk_required_use_node(data):
    if data[0] == '!':
        return values.ContainmentMatch(data[1:], negate=True)
    return values.ContainmentMatch(data,)

def generate_required_use(self):
    data = self.data.pop("REQUIRED_USE", "")
    if not self.eapi_obj.options.has_required_use:
        data = ''
    operators = {
        "||":boolean.OrRestriction,
        "":boolean.AndRestriction,
        "^^":boolean.JustOneRestriction
    }
    if self.eapi_obj.options.required_use_one_of:
        operators['??'] = boolean.AtMostOneOfRestriction

    return conditionals.DepSet.parse(data,
        values.ContainmentMatch, operators=operators,
        element_func=_mk_required_use_node,
        )

def generate_providers(self):
    rdep = AndRestriction(self.versioned_atom)
    func = partial(virtual_ebuild, self._parent, self,
        {"rdepends":rdep, "slot":"%s-%s" % (self.category, self.version)})
    # re-enable license at some point.
    #, "license":self.license})

    return conditionals.DepSet.parse(
        self.data.pop("PROVIDE", ""), virtual_ebuild, element_func=func,
        operators={"":boolean.AndRestriction})

def generate_fetchables(self, allow_missing_checksums=False):
    chksums_can_be_missing = allow_missing_checksums or \
        bool(getattr(self.repo, '_allow_missing_chksums', False))
    chksums_can_be_missing, chksums = self.repo._get_digests(self,
        allow_missing=chksums_can_be_missing)

    mirrors = getattr(self._parent, "mirrors", {})
    default_mirrors = getattr(self._parent, "default_mirrors", None)
    common = {}
    func = partial(create_fetchable_from_uri, self, chksums,
        chksums_can_be_missing, mirrors, default_mirrors, common)
    d = conditionals.DepSet.parse(
        self.data.pop("SRC_URI", ""), fetchable, operators={},
        element_func=func,
        allow_src_uri_file_renames=self.eapi_obj.options.src_uri_renames)
    for v in common.itervalues():
        v.uri.finalize()
    return d

# utility func.
def create_fetchable_from_uri(pkg, chksums, ignore_missing_chksums, mirrors,
                              default_mirrors, common_files, uri, filename=None):
    if filename is None:
        filename = os.path.basename(uri)

    preexisting = common_files.get(filename)

    if preexisting is None:
        if filename not in chksums and not ignore_missing_chksums:
            raise MissingChksum(filename)
        uris = uri_list(filename)
    else:
        uris = preexisting.uri

    if filename != uri:
        if preexisting is None:
            if "primaryuri" not in pkg.restrict:
                if default_mirrors and "mirror" not in pkg.restrict:
                    uris.add_mirror(default_mirrors)

        if uri.startswith("mirror://"):
            # mirror:// is 9 chars.

            tier, remaining_uri = uri[9:].split("/", 1)

            if tier not in mirrors:
                raise UnknownMirror(tier, remaining_uri)

            uris.add_mirror(mirrors[tier], remaining_uri)

        else:
            uris.add_uri(uri)
        if preexisting is None and "primaryuri" in pkg.restrict:
            if default_mirrors and "mirror" not in pkg.restrict:
                uris.add_mirror(default_mirrors)

    if preexisting is None:
        common_files[filename] = fetchable(filename, uris, chksums.get(filename))
    return common_files[filename]

def get_parsed_eapi(self):
    ebuild = self.ebuild
    eapi = None
    if ebuild.path:
        # Use readlines directly since it does whitespace stripping
        # for us, far faster than native python can.
        i = fileutils.readlines_utf8(ebuild.path)
    else:
        i = (x.strip() for x in ebuild.text_fileobj())
    for line in i:
        if line[0:1] in ('', '#'):
            continue
        eapi = _parse_EAPI_RE.match(line)
        break
    return get_eapi(eapi.group(2) if eapi is not None else '0', True)

def get_slot(self):
    o = self.data.pop("SLOT", "0")
    if o is None:
        raise ValueError(self, "SLOT cannot be unset")
    return o.strip()

def get_subslot(self):
    slot, separator, subslot = self.fullslot.partition('/')
    if not subslot:
        return slot
    return subslot

def rewrite_restrict(restrict):
    if restrict[0:2] == 'no':
        return restrict[2:]
    return restrict

def get_repo_id(self):
    return self.repo.repo_id

def get_inherited(self):
    return tuple(sorted(self.data.get('_eclasses_', {})))


class base(metadata.package):

    """
    ebuild package

    :cvar _config_wrappables: mapping of attribute to callable for
        re-evaluating attributes dependent on configuration
    """

    _config_wrappables = dict((x, klass.alias_method("evaluate_depset"))
        for x in ["depends", "rdepends", "post_rdepends", "fetchables",
                  "license", "src_uri", "provides", "restrict",
                  "required_use"])

    _get_attr = dict(metadata.package._get_attr)
    _get_attr["provides"] = generate_providers
    _get_attr["depends"] = partial(generate_depset, atom, "DEPEND", False)
    _get_attr["rdepends"] = partial(generate_depset, atom, "RDEPEND", False)
    _get_attr["post_rdepends"] = partial(generate_depset, atom, "PDEPEND", False)
    _get_attr["license"] = partial(generate_depset, str,
        "LICENSE", True, element_func=intern)
    _get_attr["fullslot"] = get_slot
    _get_attr["slot"] = lambda s:s.fullslot.partition('/')[0]
    _get_attr["subslot"] = get_subslot
    _get_attr["fetchables"] = generate_fetchables
    _get_attr["description"] = lambda s:s.data.pop("DESCRIPTION", "").strip()
    _get_attr["keywords"] = lambda s:tuple(map(intern,
        s.data.pop("KEYWORDS", "").split()))
    _get_attr["restrict"] = lambda s:conditionals.DepSet.parse(
        s.data.pop("RESTRICT", ''), str, operators={},
        element_func=rewrite_restrict)
    _get_attr["eapi_obj"] = get_parsed_eapi
    _get_attr["iuse"] = lambda s:frozenset(imap(intern,
        s.data.pop("IUSE", "").split()))
    _get_attr["iuse_effective"] = lambda s:s
    _get_attr["properties"] = lambda s:frozenset(imap(intern,
        s.data.pop("PROPERTIES", "").split()))
    _get_attr["defined_phases"] = lambda s:s.eapi_obj.interpret_cache_defined_phases(imap(intern,
        s.data.pop("DEFINED_PHASES", "").split()))
    _get_attr["homepage"] = lambda s:s.data.pop("HOMEPAGE", "").strip()
    _get_attr["inherited"] = get_inherited
    _get_attr["required_use"] = generate_required_use
    _get_attr["source_repository"] = get_repo_id

    __slots__ = tuple(_get_attr.keys() + ["_pkg_metadata_shared"])

    PN = klass.alias_attr("package")
    repo_id = klass.alias_attr("repo.repo_id")
    is_supported = klass.alias_attr('eapi_obj.is_supported')
    tracked_attributes = klass.alias_attr('eapi_obj.tracked_attributes')

    @property
    def eapi(self):
        eapi_obj = self.eapi_obj
        if eapi_obj is not None:
            return int(eapi_obj.magic)
        return "unsupported"

    @property
    def mandatory_phases(self):
        return frozenset(
            chain(self.defined_phases, self.eapi_obj.default_phases))

    @property
    def P(self):
        return "%s-%s" % (self.package, self.version)

    @property
    def PF(self):
        return "%s-%s" % (self.package, self.fullver)

    @property
    def PR(self):
        r = self.revision
        if r is not None:
            return r
        return 0

    @property
    def path(self):
        return self._parent._get_ebuild_path(self)

    @property
    def ebuild(self):
        return self._parent.get_ebuild_src(self)

    def _fetch_metadata(self, ebp=None, force_regen=None):
        return self._parent._get_metadata(self, ebp=ebp, force_regen=force_regen)

    def __str__(self):
        return "ebuild src: %s" % self.cpvstr

    def __repr__(self):
        return "<%s cpv=%r @%#8x>" % (self.__class__, self.cpvstr, id(self))


class package(base):

    __slots__ = ("_shared_pkg_data",)

    _get_attr = dict(base._get_attr)

    def __init__(self, shared_pkg_data, *args, **kwargs):
        base.__init__(self, *args, **kwargs)
        object.__setattr__(self, "_shared_pkg_data", shared_pkg_data)

    maintainers = klass.alias_attr("_shared_pkg_data.metadata_xml.maintainers")
    herds = klass.alias_attr("_shared_pkg_data.metadata_xml.herds")
    longdescription = klass.alias_attr("_shared_pkg_data.metadata_xml.longdescription")
    manifest = klass.alias_attr("_shared_pkg_data.manifest")

    @property
    def _mtime_(self):
        return self._parent._get_ebuild_mtime(self)

    @property
    def environment(self):
        data = self._get_ebuild_environment()
        return data_source.data_source(data, mutable=False)

    def _get_ebuild_environment(self, ebp=None):
        with processor.reuse_or_request(ebp) as ebp:
            return ebp.get_ebuild_environment(self, self.repo.eclass_cache)


class package_factory(metadata.factory):
    child_class = package

    # For the plugin system.
    priority = 5

    def __init__(self, parent, cachedb, eclass_cache, mirrors, default_mirrors,
                 *args, **kwargs):
        super(package_factory, self).__init__(parent, *args, **kwargs)
        self._cache = cachedb
        self._ecache = eclass_cache

        if mirrors:
            mirrors = dict((k, mirror(v, k)) for k, v in mirrors.iteritems())

        self.mirrors = mirrors
        if default_mirrors:
            self.default_mirrors = default_mirror(default_mirrors,
                "conf. default mirror")
        else:
            self.default_mirrors = None

    def get_ebuild_src(self, pkg):
        return self._parent_repo._get_ebuild_src(pkg)

    def _get_ebuild_path(self, pkg):
        return self._parent_repo._get_ebuild_path(pkg)

    def _get_ebuild_mtime(self, pkg):
        return os.stat(self._get_ebuild_path(pkg)).st_mtime

    def _get_metadata(self, pkg, ebp=None, force_regen=False):
        caches = self._cache
        if force_regen:
            caches = ()
        ebuild_hash = chksum.LazilyHashedPath(pkg.path)
        for cache in caches:
            if cache is not None:
                try:
                    data = cache[pkg.cpvstr]
                    if cache.validate_entry(data, ebuild_hash, self._ecache):
                        return data
                    if not cache.readonly:
                        del cache[pkg.cpvstr]
                except KeyError:
                    continue
                except cache_errors.CacheError, ce:
                    logger.warning("caught cache error: %s" % ce)
                    del ce
                    continue

        # no cache entries, regen
        return self._update_metadata(pkg, ebp=ebp)

    def _update_metadata(self, pkg, ebp=None):
        parsed_eapi = pkg.eapi_obj
        if not parsed_eapi.is_supported:
            return {'EAPI':parsed_eapi.magic}

        with processor.reuse_or_request(ebp) as my_proc:
            mydata = my_proc.get_keys(pkg, self._ecache)

        inherited = mydata.pop("INHERITED", None)
        # rewrite defined_phases as needed, since we now know the eapi.
        eapi = get_eapi(mydata["EAPI"])
        if parsed_eapi != eapi:
            raise metadata_errors.MetadataException(
                pkg, 'eapi', "parsed eapi doesn't match sourced eapi")
        wipes = set(mydata)

        wipes.difference_update(eapi.metadata_keys)
        if mydata["DEFINED_PHASES"] != '-':
            phases = mydata["DEFINED_PHASES"].split()
            d = eapi.phases_rev
            phases = set(d.get(x) for x in phases)
            # discard is required should we have gotten
            # a phase that isn't actually in this eapi
            phases.discard(None)
            mydata["DEFINED_PHASES"] = ' '.join(sorted(phases))

        if inherited:
            mydata["_eclasses_"] = self._ecache.get_eclass_data(
                inherited.split())
        else:
            mydata["_eclasses_"] = {}
        mydata['_chf_'] = chksum.LazilyHashedPath(pkg.path)

        for x in wipes:
            del mydata[x]

        if self._cache is not None:
            for cache in self._cache:
                if not cache.readonly:
                    try:
                        cache[pkg.cpvstr] = mydata
                    except cache_errors.CacheError, ce:
                        logger.warning("caught cache error: %s" % ce)
                        del ce
                        continue
                    break

        return mydata

    def new_package(self, *args):
        inst = self._cached_instances.get(args)
        if inst is None:
            # key being cat/pkg
            mxml = self._parent_repo._get_shared_pkg_data(args[0], args[1])
            inst = self._cached_instances[args] = self.child_class(
                mxml, self, *args)
        return inst


generate_new_factory = package_factory


class virtual_ebuild(metadata.package):

    """
    PROVIDES generated fake packages
    """

    package_is_real = False
    built = True

    #__slots__ = ("_orig_data", "data", "provider")
    __slotting_intentionally_disabled__ = True

    def __init__(self, parent_repository, pkg, data, cpvstr):
        """
        :param cpvstr: cpv for the new pkg
        :param parent_repository: actual repository that this pkg should
            claim it belongs to
        :param pkg: parent pkg that is generating this pkg
        :param data: mapping of data to push to use in __getattr__ access
        """
        c = CPV.unversioned(cpvstr)
        if c.fullver is None:
            cpvstr = cpvstr + "-" + pkg.fullver

        metadata.package.__init__(self, parent_repository, cpvstr)
        sfunc = object.__setattr__
        sfunc(self, "data", IndeterminantDict(lambda *a: str(), data))
        sfunc(self, "_orig_data", data)
        sfunc(self, "provider", pkg.versioned_atom)
        sfunc(self, "eapi_obj", get_eapi("0"))

    def __getattr__(self, attr):
        if attr in self._orig_data:
            return self._orig_data[attr]
        return metadata.package.__getattr__(self, attr)

    _get_attr = package._get_attr.copy()

    # we have to duplicate this here since the virtual
    # doesn't directly derive from base
    @property
    def eapi(self):
        return int(self.eapi_obj.magic)

