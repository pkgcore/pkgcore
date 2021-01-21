"""
package class for buildable ebuilds
"""

__all__ = ("base", "package", "package_factory")

import os
from functools import partial
from itertools import chain
from sys import intern

from snakeoil import chksum, data_source, fileutils, klass
from snakeoil.demandload import demand_compile_regexp
from snakeoil.mappings import OrderedFrozenSet

from .. import fetch
from ..cache import errors as cache_errors
from ..log import logger
from ..package import errors as metadata_errors
from ..package import metadata
from ..package.base import DynamicGetattrSetter
from ..restrictions import boolean, values
from . import conditionals
from . import errors as ebuild_errors
from . import processor
from .atom import atom
from .eapi import get_eapi
from .misc import sort_keywords

demand_compile_regexp(
    '_EAPI_regex', r"^EAPI=(['\"]?)(?P<EAPI>[A-Za-z0-9+_.-]*)\1[\t ]*(?:#.*)?")
demand_compile_regexp(
    '_EAPI_str_regex', r"^EAPI=(['\"]?)(?P<EAPI>.*)\1")


class base(metadata.package):
    """ebuild package

    :cvar _config_wrappables: mapping of attribute to callable for
        re-evaluating attributes dependent on configuration
    """

    _config_wrappables = {
        x: klass.alias_method("evaluate_depset")
        for x in (
            "bdepend", "depend", "rdepend", "pdepend",
            "fetchables", "license", "restrict", "required_use",
        )
    }

    __slots__ = ('_pkg_metadata_shared',)

    def _generate_depset(self, kls, key):
        return conditionals.DepSet.parse(
            self.data.pop(key, ""), kls,
            attr=key, element_func=self.eapi.atom_kls,
            transitive_use_atoms=self.eapi.options.transitive_use_atoms)

    @DynamicGetattrSetter.register
    def bdepend(self):
        if "BDEPEND" in self.eapi.metadata_keys:
            return self._generate_depset(atom, "BDEPEND")
        return conditionals.DepSet()

    @DynamicGetattrSetter.register
    def depend(self):
        return self._generate_depset(atom, "DEPEND")

    @DynamicGetattrSetter.register
    def rdepend(self):
        return self._generate_depset(atom, "RDEPEND")

    @DynamicGetattrSetter.register
    def pdepend(self):
        return self._generate_depset(atom, "PDEPEND")

    @DynamicGetattrSetter.register
    def license(self):
        return conditionals.DepSet.parse(
            self.data.pop('LICENSE', ''), str,
            operators={
                '||': boolean.OrRestriction,
                '': boolean.AndRestriction},
            attr='LICENSE', element_func=intern)

    @DynamicGetattrSetter.register
    def fullslot(self):
        slot = self.data.get('SLOT', None)
        if not slot:
            raise metadata_errors.MetadataException(
                self, 'slot', 'SLOT cannot be unset or empty')
        if not self.eapi.valid_slot_regex.match(slot):
            raise metadata_errors.MetadataException(
                self, 'slot', f'invalid SLOT: {slot!r}')
        return slot

    @DynamicGetattrSetter.register
    def subslot(self):
        slot, _sep, subslot = self.fullslot.partition('/')
        if not subslot:
            return slot
        return subslot

    @DynamicGetattrSetter.register
    def slot(self):
        return self.fullslot.partition('/')[0]

    def create_fetchable_from_uri(
            self, chksums, ignore_missing_chksums, ignore_unknown_mirrors,
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
                raise metadata_errors.MissingChksum(self, filename)
            uris = fetch.uri_list(filename)
        else:
            uris = preexisting.uri

        if filename != uri:
            if preexisting is None:
                if "primaryuri" not in self.restrict:
                    if default_mirrors and "mirror" not in self.restrict:
                        uris.add_mirror(default_mirrors)

            if uri.startswith("mirror://"):
                # mirror:// is 9 chars.
                tier, remaining_uri = uri[9:].split("/", 1)
                mirror = mirrors.get(tier, fetch.unknown_mirror(tier))
                uris.add_mirror(mirror, sub_uri=remaining_uri)

            else:
                uris.add_uri(uri)
            if preexisting is None and "primaryuri" in self.restrict:
                if default_mirrors and "mirror" not in self.restrict:
                    uris.add_mirror(default_mirrors)

        if preexisting is None:
            common_files[filename] = fetch.fetchable(filename, uris, chksums.get(filename))
        return common_files[filename]

    def generate_fetchables(self, allow_missing_checksums=False,
                            ignore_unknown_mirrors=False, skip_default_mirrors=False):
        """Generate fetchables object for a package."""
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
            self.create_fetchable_from_uri, chksums,
            chksums_can_be_missing, ignore_unknown_mirrors,
            mirrors, default_mirrors, common)

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

    @DynamicGetattrSetter.register
    def fetchables(self):
        return self.generate_fetchables()

    @DynamicGetattrSetter.register
    def distfiles(self):
        def _extract_distfile_from_uri(uri, filename=None):
            if filename is not None:
                return filename
            return os.path.basename(uri)
        return conditionals.DepSet.parse(
            self.data.get("SRC_URI", ''), str, operators={}, attr='SRC_URI',
            element_func=partial(_extract_distfile_from_uri),
            allow_src_uri_file_renames=self.eapi.options.src_uri_renames)

    @DynamicGetattrSetter.register
    def description(self):
        return self.data.pop("DESCRIPTION", "").strip()

    @DynamicGetattrSetter.register
    def keywords(self):
        return tuple(map(intern, self.data.pop("KEYWORDS", "").split()))

    @property
    def sorted_keywords(self):
        """Sort keywords with prefix keywords after regular arches."""
        return tuple(sort_keywords(self.keywords))

    @DynamicGetattrSetter.register
    def restrict(self):
        return conditionals.DepSet.parse(
            self.data.pop("RESTRICT", ''), str, operators={},
            attr='RESTRICT')

    @DynamicGetattrSetter.register
    def eapi(self):
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
            if (mo := _EAPI_str_regex.match(line)) and (eapi_str := mo.group('EAPI')):
                eapi = _EAPI_regex.match(line).group('EAPI')
            break
        try:
            return get_eapi(eapi)
        except ValueError as e:
            error = str(e) if eapi else f'{e}: {eapi_str!r}'
            raise metadata_errors.MetadataException(self, 'eapi', error)

    is_supported = klass.alias_attr('eapi.is_supported')
    tracked_attributes = klass.alias_attr('eapi.tracked_attributes')

    @DynamicGetattrSetter.register
    def iuse(self):
        return frozenset(map(intern, self.data.pop("IUSE", "").split()))

    @property
    def iuse_stripped(self):
        if self.eapi.options.iuse_defaults:
            return frozenset(x.lstrip('-+') if len(x) > 1 else x for x in self.iuse)
        return self.iuse

    iuse_effective = klass.alias_attr("iuse_stripped")

    @DynamicGetattrSetter.register
    def user_patches(self):
        return ()

    @DynamicGetattrSetter.register
    def properties(self):
        return conditionals.DepSet.parse(
            self.data.pop("PROPERTIES", ''), str, operators={},
            attr='PROPERTIES')

    @DynamicGetattrSetter.register
    def defined_phases(self):
        return self.eapi.interpret_cache_defined_phases(
            map(intern, self.data.pop("DEFINED_PHASES", "").split()))

    @DynamicGetattrSetter.register
    def homepage(self):
        return tuple(self.data.pop("HOMEPAGE", "").split())

    @DynamicGetattrSetter.register
    def inherited(self):
        """Ordered set of all inherited eclasses."""
        return OrderedFrozenSet(self.data.get("_eclasses_", ()))

    @DynamicGetattrSetter.register
    def inherit(self):
        """Ordered set of directly inherited eclasses."""
        return OrderedFrozenSet(self.data.get("INHERIT", "").split())

    @staticmethod
    def _mk_required_use_node(data):
        if data[0] == '!':
            return values.ContainmentMatch2(data[1:], negate=True)
        return values.ContainmentMatch2(data)

    @DynamicGetattrSetter.register
    def required_use(self):
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
                    element_func=self._mk_required_use_node, attr='REQUIRED_USE')
        return conditionals.DepSet()

    source_repository = klass.alias_attr("repo.repo_id")

    PN = klass.alias_attr("package")
    PV = klass.alias_attr("version")
    PVR = klass.alias_attr("fullver")

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

        if inherited := mydata.pop("INHERITED", None):
            mydata["_eclasses_"] = self._ecache.get_eclass_data(inherited.split())
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
        if self._parent_repo.package_cache:
            inst = self._cached_instances.get(args)
        else:
            # package caching is disabled
            inst = None

        if inst is None:
            # key being cat/pkg
            mxml = self._parent_repo._get_shared_pkg_data(args[0], args[1])
            inst = self._cached_instances[args] = self.child_class(
                mxml, self, *args)

        return inst


generate_new_factory = package_factory
