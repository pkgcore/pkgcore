"""
package class for buildable ebuilds
"""

__all__ = ("base", "package", "package_factory")

from functools import partial
from itertools import chain
import os
from sys import intern

from snakeoil import chksum, data_source, fileutils, klass
from snakeoil.demandload import demand_compile_regexp
from snakeoil.sequences import iflatten_instance

from pkgcore import fetch
from pkgcore.cache import errors as cache_errors
from pkgcore.ebuild import conditionals, const, processor, errors as ebuild_errors
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.eapi import get_eapi
from pkgcore.ebuild.misc import sort_keywords
from pkgcore.log import logger
from pkgcore.package import errors as metadata_errors, metadata
from pkgcore.restrictions import boolean, values


demand_compile_regexp(
    '_EAPI_regex', r"^EAPI=(['\"]?)(?P<EAPI>[A-Za-z0-9+_.-]*)\1[\t ]*(?:#.*)?")
demand_compile_regexp(
    '_EAPI_str_regex', r"^EAPI=(['\"]?)(?P<EAPI>.*)\1")
demand_compile_regexp('_parse_inherit_regex', r'^\s*inherit\s(?P<eclasses>.*?)(#.*)?$')


def generate_depset(kls, key, self):
    return conditionals.DepSet.parse(
        self.data.pop(key, ""), kls,
        attr=key, element_func=self.eapi.atom_kls,
        transitive_use_atoms=self.eapi.options.transitive_use_atoms)


def generate_licenses(self):
    return conditionals.DepSet.parse(
        self.data.pop('LICENSE', ''), str,
        operators={
            '||': boolean.OrRestriction,
            '': boolean.AndRestriction},
        attr='LICENSE', element_func=intern)


def _mk_required_use_node(data):
    if data[0] == '!':
        return values.ContainmentMatch2(data[1:], negate=True)
    return values.ContainmentMatch2(data)


def generate_required_use(self):
    if self.eapi.options.has_required_use:
        data = self.data.pop("REQUIRED_USE", "")
        if data:
            operators = {
                "||": boolean.OrRestriction,
                "": boolean.AndRestriction,
                "^^": boolean.JustOneRestriction
            }

            def _invalid_op(msg, *args):
                raise metadata_errors.MetadataException(self, 'eapi', f'REQUIRED_USE: {msg}')

            if self.eapi.options.required_use_one_of:
                operators['??'] = boolean.AtMostOneOfRestriction
            else:
                operators['??'] = partial(
                    _invalid_op, f"EAPI '{self.eapi}' doesn't support '??' operator")

            return conditionals.DepSet.parse(
                data,
                values.ContainmentMatch2, operators=operators,
                element_func=_mk_required_use_node, attr='REQUIRED_USE')
    return conditionals.DepSet()


def generate_fetchables(self, allow_missing_checksums=False,
                        ignore_unknown_mirrors=False, skip_default_mirrors=False):
    chksums_can_be_missing = allow_missing_checksums or \
        bool(getattr(self.repo, '_allow_missing_chksums', False))
    chksums_can_be_missing, chksums = self.repo._get_digests(
        self, allow_missing=chksums_can_be_missing)

    mirrors = getattr(self._parent, "mirrors", {})
    if skip_default_mirrors:
        default_mirrors = None
    else:
        default_mirrors = getattr(self._parent, "default_mirrors", None)
    common = {}
    func = partial(
        create_fetchable_from_uri, self, chksums,
        chksums_can_be_missing, ignore_unknown_mirrors,
        mirrors, default_mirrors, common)

    # TODO: try/except block can be dropped when pkg._get_attr['fetchables']
    # filtering hacks to pass custom args are fixed/removed.
    #
    # Usually dynamic_getattr_dict() catches/rethrows all exceptions as
    # MetadataExceptions when attrs are accessed properly (e.g. pkg.fetchables).
    try:
        d = conditionals.DepSet.parse(
            self.data.get("SRC_URI", ""), fetch.fetchable, operators={},
            element_func=func, attr='SRC_URI',
            allow_src_uri_file_renames=self.eapi.options.src_uri_renames)
    except ebuild_errors.DepsetParseError as e:
        raise metadata_errors.MetadataException(self, 'fetchables', str(e))

    for v in common.values():
        v.uri.finalize()
    return d


def generate_distfiles(self):
    def _extract_distfile_from_uri(uri, filename=None):
        if filename is not None:
            return filename
        return os.path.basename(uri)
    return conditionals.DepSet.parse(
        self.data.get("SRC_URI", ''), str, operators={}, attr='SRC_URI',
        element_func=partial(_extract_distfile_from_uri),
        allow_src_uri_file_renames=self.eapi.options.src_uri_renames)


# utility func.
def create_fetchable_from_uri(pkg, chksums, ignore_missing_chksums, ignore_unknown_mirrors,
                              mirrors, default_mirrors, common_files, uri, filename=None):
    default_filename = os.path.basename(uri)
    if filename is not None:
        # log redundant renames for pkgcheck to flag
        if filename == default_filename:
            logger.info(f'redundant rename: {uri} -> {filename}')
    else:
        filename = default_filename

    if not filename:
        raise ValueError(f'missing filename: {uri!r}')

    preexisting = common_files.get(filename)

    if preexisting is None:
        if filename not in chksums and not ignore_missing_chksums:
            raise metadata_errors.MissingChksum(pkg, filename)
        uris = fetch.uri_list(filename)
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
            mirror = mirrors.get(tier, fetch.unknown_mirror(tier))
            uris.add_mirror(mirror, sub_uri=remaining_uri)

        else:
            uris.add_uri(uri)
        if preexisting is None and "primaryuri" in pkg.restrict:
            if default_mirrors and "mirror" not in pkg.restrict:
                uris.add_mirror(default_mirrors)

    if preexisting is None:
        common_files[filename] = fetch.fetchable(filename, uris, chksums.get(filename))
    return common_files[filename]


def get_parsed_eapi(self):
    ebuild = self.ebuild
    eapi = '0'
    if ebuild.path:
        # Use readlines directly since it does whitespace stripping
        # for us, far faster than native python can.
        i = fileutils.readlines_utf8(ebuild.path)
    else:
        i = (x.strip() for x in ebuild.text_fileobj())
    for line in i:
        if line[0:1] in ('', '#'):
            continue
        eapi_str = _EAPI_str_regex.match(line)
        if eapi_str is not None:
            eapi_str = eapi_str.group('EAPI')
            if eapi_str:
                eapi = _EAPI_regex.match(line).group('EAPI')
        break
    try:
        return get_eapi(eapi)
    except ValueError as e:
        raise metadata_errors.MetadataException(self, 'eapi', f'{e}: {eapi_str!r}')


def get_parsed_inherits(self):
    """Search for directly inherited eclasses in an ebuild file.

    This ignores conditional inherits since it naively uses a regex for
    simplicity.
    """
    if self.ebuild.path:
        # Use readlines directly since it does whitespace stripping
        # for us, far faster than native python can.
        i = fileutils.readlines_utf8(self.ebuild.path)
    else:
        i = (x.strip() for x in self.ebuild.text_fileobj())

    # get all inherit line matches in the ebuild file
    matches = filter(None, map(_parse_inherit_regex.match, i))
    # and return the directly inherited eclasses in the order they're seen
    return tuple(chain.from_iterable(m.group('eclasses').split() for m in matches))


def get_slot(self):
    slot = self.data.pop('SLOT', None)
    if not slot:
        raise metadata_errors.MetadataException(
            self, 'slot', 'SLOT cannot be unset or empty')
    if not self.eapi.valid_slot_regex.match(slot):
        raise metadata_errors.MetadataException(
            self, 'slot', f'invalid SLOT: {slot!r}')
    return slot


def get_subslot(self):
    slot, _sep, subslot = self.fullslot.partition('/')
    if not subslot:
        return slot
    return subslot


def get_bdepend(self):
    if "BDEPEND" in self.eapi.metadata_keys:
        return generate_depset(atom, "BDEPEND", self)
    return conditionals.DepSet()


class base(metadata.package):
    """ebuild package

    :cvar _config_wrappables: mapping of attribute to callable for
        re-evaluating attributes dependent on configuration
    """

    _config_wrappables = {
        x: klass.alias_method("evaluate_depset")
        for x in (
            "bdepend", "depend", "rdepend", "pdepend",
            "fetchables", "license", "src_uri", "restrict", "required_use",
        )
    }

    _get_attr = dict(metadata.package._get_attr)
    _get_attr["bdepend"] = get_bdepend
    _get_attr["depend"] = partial(generate_depset, atom, "DEPEND")
    _get_attr["rdepend"] = partial(generate_depset, atom, "RDEPEND")
    _get_attr["pdepend"] = partial(generate_depset, atom, "PDEPEND")
    _get_attr["license"] = generate_licenses
    _get_attr["fullslot"] = get_slot
    _get_attr["slot"] = lambda s: s.fullslot.partition('/')[0]
    _get_attr["subslot"] = get_subslot
    _get_attr["fetchables"] = generate_fetchables
    _get_attr["distfiles"] = generate_distfiles
    _get_attr["description"] = lambda s: s.data.pop("DESCRIPTION", "").strip()
    _get_attr["keywords"] = lambda s: tuple(
        map(intern, s.data.pop("KEYWORDS", "").split()))
    _get_attr["restrict"] = lambda s: conditionals.DepSet.parse(
        s.data.pop("RESTRICT", ''), str, operators={}, attr='RESTRICT')
    _get_attr["eapi"] = get_parsed_eapi
    _get_attr["iuse"] = lambda s: frozenset(
        map(intern, s.data.pop("IUSE", "").split()))
    _get_attr["user_patches"] = lambda s: ()
    _get_attr["iuse_effective"] = lambda s: s.iuse_stripped
    _get_attr["properties"] = lambda s: conditionals.DepSet.parse(
        s.data.pop("PROPERTIES", ''), str, operators={}, attr='PROPERTIES')
    _get_attr["defined_phases"] = lambda s: s.eapi.interpret_cache_defined_phases(
        map(intern, s.data.pop("DEFINED_PHASES", "").split()))
    _get_attr["homepage"] = lambda s: tuple(s.data.pop("HOMEPAGE", "").split())
    _get_attr["inherited"] = lambda s: tuple(sorted(s.data.get('_eclasses_', {})))
    _get_attr["inherit"] = get_parsed_inherits

    _get_attr["required_use"] = generate_required_use
    _get_attr["source_repository"] = lambda s: s.repo.repo_id

    __slots__ = tuple(list(_get_attr.keys()) + ["_pkg_metadata_shared"])

    PN = klass.alias_attr("package")
    PV = klass.alias_attr("version")
    PVR = klass.alias_attr("fullver")

    is_supported = klass.alias_attr('eapi.is_supported')
    tracked_attributes = klass.alias_attr('eapi.tracked_attributes')

    @property
    def sorted_keywords(self):
        """Sort keywords with prefix keywords after regular arches."""
        return tuple(sort_keywords(self.keywords))

    @property
    def iuse_stripped(self):
        if self.eapi.options.iuse_defaults:
            return frozenset(x.lstrip('-+') if len(x) > 1 else x for x in self.iuse)
        return self.iuse

    @property
    def mandatory_phases(self):
        return frozenset(
            chain(self.defined_phases, self.eapi.default_phases))

    @property
    def live(self):
        return 'live' in self.properties

    @property
    def P(self):
        return f"{self.package}-{self.version}"

    @property
    def PF(self):
        return f"{self.package}-{self.fullver}"

    @property
    def PR(self):
        return f'r{self.revision}'

    @property
    def path(self):
        return self._parent._get_ebuild_path(self)

    @property
    def ebuild(self):
        return self._parent.get_ebuild_src(self)

    def _fetch_metadata(self, ebp=None, force_regen=None):
        return self._parent._get_metadata(self, ebp=ebp, force_regen=force_regen)

    def __str__(self):
        return f"ebuild src: {self.cpvstr}"

    def __repr__(self):
        return "<%s cpv=%r @%#8x>" % (self.__class__, self.cpvstr, id(self))


class package(base):

    __slots__ = ("_shared_pkg_data",)

    _get_attr = dict(base._get_attr)

    def __init__(self, shared_pkg_data, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "_shared_pkg_data", shared_pkg_data)

    maintainers = klass.alias_attr("_shared_pkg_data.metadata_xml.maintainers")
    local_use = klass.alias_attr("_shared_pkg_data.metadata_xml.local_use")
    longdescription = klass.alias_attr("_shared_pkg_data.metadata_xml.longdescription")
    manifest = klass.alias_attr("_shared_pkg_data.manifest")
    stabilize_allarches = klass.alias_attr("_shared_pkg_data.metadata_xml.stabilize_allarches")

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
        super().__init__(parent, *args, **kwargs)
        self._cache = cachedb
        self._ecache = eclass_cache

        if mirrors:
            mirrors = {k: fetch.mirror(v, k) for k, v in mirrors.items()}

        self.mirrors = mirrors
        if default_mirrors:
            self.default_mirrors = fetch.default_mirror(default_mirrors, "conf. default mirror")
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
                except cache_errors.CacheError as e:
                    logger.warning("caught cache error: %s", e)
                    del e
                    continue

        # no cache entries, regen
        return self._update_metadata(pkg, ebp=ebp)

    def _update_metadata(self, pkg, ebp=None):
        parsed_eapi = pkg.eapi
        if not parsed_eapi.is_supported:
            return {'EAPI': str(parsed_eapi)}

        with processor.reuse_or_request(ebp) as my_proc:
            try:
                mydata = my_proc.get_keys(pkg, self._ecache)
            except processor.ProcessorError as e:
                raise metadata_errors.MetadataException(
                    pkg, 'data', 'failed sourcing ebuild', e)

        inherited = mydata.pop("INHERITED", None)
        # Rewrite defined_phases as needed, since we now know the EAPI.
        eapi = get_eapi(mydata.get('EAPI', '0'))
        if parsed_eapi != eapi:
            raise metadata_errors.MetadataException(
                pkg, 'eapi',
                f"parsed EAPI '{parsed_eapi}' doesn't match sourced EAPI '{eapi}'")
        wipes = set(mydata)

        wipes.difference_update(eapi.metadata_keys)
        if mydata["DEFINED_PHASES"] != '-':
            phases = mydata["DEFINED_PHASES"].split()
            d = eapi.phases_rev
            phases = set(d.get(x) for x in phases)
            # Discard is required should we have gotten
            # a phase that isn't actually in this EAPI.
            phases.discard(None)
            mydata["DEFINED_PHASES"] = ' '.join(sorted(phases))

        if inherited:
            mydata["_eclasses_"] = self._ecache.get_eclass_data(
                inherited.split())
        mydata['_chf_'] = chksum.LazilyHashedPath(pkg.path)

        for x in wipes:
            del mydata[x]

        if self._cache is not None:
            for cache in self._cache:
                if not cache.readonly:
                    try:
                        cache[pkg.cpvstr] = mydata
                    except cache_errors.CacheError as e:
                        logger.warning("caught cache error: %s", e)
                        del e
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
