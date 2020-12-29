import os
import re
import subprocess
import sys
from collections import defaultdict
from functools import partial

from snakeoil import klass, mappings, weakrefs
from snakeoil.demandload import demand_compile_regexp
from snakeoil.osutils import pjoin
from snakeoil.process.spawn import bash_version

from ..log import logger
from . import atom, const

demand_compile_regexp(
    '_valid_EAPI_regex', r"^[A-Za-z0-9_][A-Za-z0-9+_.-]*$"
)


eapi_optionals = mappings.ImmutableDict({
    # Controls what version of bash compatibility to force; see PMS.
    "bash_compat": '3.2',

    # Controls whether -r is allowed for dodoc.
    "dodoc_allow_recursive": False,

    # Controls the language awareness of doman; see PMS.
    "doman_language_detect": False,

    # Controls whether -i18n option is allowed.
    "doman_language_override": False,

    # Controls whether an ebuild_phase function exists for ebuild consumption.
    'ebuild_phase_func': False,

    # Controls whether REPLACING vars are exported to ebuilds; see PMS.
    "exports_replacing": False,

    # Controls of whether failglob is enabled globally; see PMS.
    "global_failglob": False,

    # Controls whether MERGE vars are exported to ebuilds; see PMS.
    "has_merge_type": False,

    # Controls whether PORTDIR and ECLASSDIR are exported to ebuilds; see PMS.
    "has_portdir": True,

    # Controls whether DESTTREE and INSDESTTREE are exported during src_install; see PMS.
    "has_desttree": True,

    # Controls whether ROOT, EROOT, D, and ED end with a trailing slash; see PMS.
    "trailing_slash": os.sep,

    # Controls whether SYSROOT, ESYSROOT, and BROOT are defined; see PMS.
    "has_sysroot": False,

    # Controls whether package.provided files in profiles are supported; see PMS.
    "profile_pkg_provided": True,

    # Controls whether package.mask and other files in profiles can
    # be directories; see PMS.
    "has_profile_data_dirs": False,

    # Controls whether REQUIRED_USE is supported, enforcing constraints on
    # allowed use configuration states.
    "has_required_use": False,

    # Controls whether USE dependency defaults are supported, see PMS.
    "has_use_dep_defaults": False,

    # Controls whether ENV_UNSET is supported, see PMS.
    "has_env_unset": False,

    # Controls whether AA env var is exported to ebuilds; this is a flattened
    # listing of each filename in SRC_URI.
    "has_AA": True,

    # Controls whether KV (kernel version; see PMS for details) is exported.
    "has_KV": True,

    # Controls whether or not pkgcore, or extensions loaded, actually fully
    # support this EAPI.
    'is_supported': True,

    # Controls whether IUSE defaults are supported; see PMS.
    'iuse_defaults': False,

    # Controls whether new* style bash functions can take their content input
    # from stdin, rather than an explicit ondisk file.
    'new_reads_stdin': False,

    # Controls whether utilities die on failure; see PMS.
    'nonfatal': True,

    # Controls whether die supports a nonfatal option; see PMS.
    "nonfatal_die": False,

    # Controls whether this EAPI supports prefix related variables/settings;
    # prefix awareness basically. See PMS for full details.
    "prefix_capable": False,

    # Controls whether profile-defined IUSE injection is supported.
    "profile_iuse_injection": False,

    # Controls whether profiles support package.use.stable.* and use.stable.* files.
    "profile_stable_use": False,

    # Controls whether has_version/best_version supports --host-root option; see PMS.
    'query_host_root': False,

    # Controls whether has_version/best_version supports -b/-d/-r options; see PMS.
    'query_deps': False,

    # Controls whether SLOT values can actually be multi-part; see PMS EAPI 5.
    # This is related to ABI breakage detection.
    'sub_slotting': False,

    # Controls whether REQUIRED_USE supports the ?? operator.
    'required_use_one_of': False,

    # Controls whether SRC_URI supports the '->' operator for url filename renaming.
    "src_uri_renames": False,

    # Controls whether or not use dependency atoms are able to control their enforced
    # value relative to another; standard use deps just enforce either on or off; EAPIs
    # supporting this allow syntax that can enforce (for example) X to be on if Y is on.
    # See PMS EAPI 4 for full details.
    "transitive_use_atoms": False,

    # Controls whether or DEFINED_PHASES is mandated for this EAPI; if so, then we can
    # trust the cache definition and skip invoking those phases if they're not defined.
    # If the EAPI didn't mandate this var, then we can do our inference, but generally will
    # invoke the phase in the absense of that metadata var since we have no other choice.
    "trust_defined_phases_cache": False,

    # Controls whether unpack supports absolute paths; see PMS.
    "unpack_absolute_paths": False,

    # Controls whether unpack supports absolute paths; see PMS.
    "unpack_case_insensitive": False,

    # Controls whether user patches are supported.
    "user_patches": False,
})


class _optionals_cls(mappings.ImmutableDict):

    mappings.inject_getitem_as_getattr(locals())


class EAPI(metaclass=klass.immutable_instance):

    known_eapis = weakrefs.WeakValCache()
    unknown_eapis = weakrefs.WeakValCache()

    def __init__(self, magic, parent=None, phases=(), default_phases=(),
                 mandatory_keys=(), dep_keys=(), metadata_keys=(),
                 eclass_keys=(), tracked_attributes=(), archive_exts=(),
                 optionals=None, ebd_env_options=None):
        sf = object.__setattr__

        sf(self, "_magic", str(magic))
        sf(self, "_parent", parent)

        sf(self, "phases", mappings.ImmutableDict(phases))
        sf(self, "phases_rev", mappings.ImmutableDict((v, k) for k, v in
           self.phases.items()))

        # We track the phases that have a default implementation- this is
        # primarily due to DEFINED_PHASES cache values not including it.
        sf(self, "default_phases", frozenset(default_phases))

        sf(self, "mandatory_keys", frozenset(mandatory_keys))
        sf(self, "dep_keys", frozenset(dep_keys))
        sf(self, "metadata_keys", (
            self.mandatory_keys | self.dep_keys | frozenset(metadata_keys)))
        # variables that eclasses have access to (used by pkgcheck eclass inherit checks)
        sf(self, "eclass_keys", self.mandatory_keys | self.dep_keys | frozenset(eclass_keys))
        sf(self, "tracked_attributes", (
            frozenset(tracked_attributes) | frozenset(x.lower() for x in dep_keys)))
        sf(self, "archive_exts", frozenset(archive_exts))

        if optionals is None:
            optionals = {}
        sf(self, 'options', _optionals_cls(optionals))
        if ebd_env_options is None:
            ebd_env_options = ()
        sf(self, "_ebd_env_options", ebd_env_options)

    @classmethod
    def register(cls, *args, **kwds):
        eapi = cls(*args, **kwds)
        pre_existing = cls.known_eapis.get(eapi._magic)
        if pre_existing is not None:
            raise ValueError(
                f"EAPI '{eapi}' is already known/instantiated- {pre_existing!r}")

        if (getattr(eapi.options, 'bash_compat', False) and
                bash_version() < eapi.options.bash_compat):
            # hard exit if the system doesn't have an adequate bash installed
            raise SystemExit(
                f"EAPI '{eapi}' requires >=bash-{eapi.options.bash_compat}, "
                f"system version: {bash_version()}")

        cls.known_eapis[eapi._magic] = eapi
        # generate EAPI bash libs when running from git repo
        eapi.bash_libs()
        return eapi

    @klass.jit_attr
    def is_supported(self):
        """Check if an EAPI is supported."""
        if EAPI.known_eapis.get(self._magic) is not None:
            if not self.options.is_supported:
                logger.warning(f"EAPI '{self}' isn't fully supported")
                sys.stderr.flush()
            return True
        return False

    @klass.jit_attr
    def bash_funcs_global(self):
        """Internally implemented global EAPI specific functions to skip when exporting."""
        # TODO: This is currently duplicated across EAPI objs, but
        # instead could be cached to a class attr.
        funcs = pjoin(const.EBD_PATH, '.generated', 'funcs', 'global')
        if not os.path.exists(funcs):
            # we're probably running in a cacheless git repo, so generate a cached version
            try:
                os.makedirs(os.path.dirname(funcs), exist_ok=True)
                with open(funcs, 'w') as f:
                    subprocess.run(
                        [pjoin(const.EBD_PATH, 'generate_global_func_list')],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f"failed to generate list of global EAPI '{self}' specific functions: {str(e)}")

        with open(funcs, 'r') as f:
            return frozenset(line.strip() for line in f)

    @klass.jit_attr
    def bash_funcs(self):
        """Internally implemented EAPI specific functions to skip when exporting."""
        funcs = pjoin(const.EBD_PATH, '.generated', 'funcs', self._magic)
        if not os.path.exists(funcs):
            # we're probably running in a cacheless git repo, so generate a cached version
            try:
                os.makedirs(os.path.dirname(funcs), exist_ok=True)
                with open(funcs, 'w') as f:
                    subprocess.run(
                        [pjoin(const.EBD_PATH, 'generate_eapi_func_list'), self._magic],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f"failed to generate list of EAPI '{self}' specific functions: {str(e)}")

        with open(funcs, 'r') as f:
            return frozenset(line.strip() for line in f)

    @klass.jit_attr
    def bash_cmds_internal(self):
        """EAPI specific commands for this EAPI."""
        cmds = pjoin(const.EBD_PATH, '.generated', 'cmds', self._magic, 'internal')
        if not os.path.exists(cmds):
            # we're probably running in a cacheless git repo, so generate a cached version
            try:
                os.makedirs(os.path.dirname(cmds), exist_ok=True)
                with open(cmds, 'w') as f:
                    subprocess.run(
                        [pjoin(const.EBD_PATH, 'generate_eapi_cmd_list'), '-i', self._magic],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f'failed to generate list of EAPI {self} internal commands: {str(e)}')

        with open(cmds, 'r') as f:
            return frozenset(line.strip() for line in f)

    @klass.jit_attr
    def bash_cmds_deprecated(self):
        """EAPI specific commands deprecated for this EAPI."""
        cmds = pjoin(const.EBD_PATH, '.generated', 'cmds', self._magic, 'deprecated')
        if not os.path.exists(cmds):
            # we're probably running in a cacheless git repo, so generate a cached version
            try:
                os.makedirs(os.path.dirname(cmds), exist_ok=True)
                with open(cmds, 'w') as f:
                    subprocess.run(
                        [pjoin(const.EBD_PATH, 'generate_eapi_cmd_list'), '-d', self._magic],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f'failed to generate list of EAPI {self} deprecated commands: {str(e)}')

        with open(cmds, 'r') as f:
            return frozenset(line.strip() for line in f)

    @klass.jit_attr
    def bash_cmds_banned(self):
        """EAPI specific commands banned for this EAPI."""
        cmds = pjoin(const.EBD_PATH, '.generated', 'cmds', self._magic, 'banned')
        if not os.path.exists(cmds):
            # we're probably running in a cacheless git repo, so generate a cached version
            try:
                os.makedirs(os.path.dirname(cmds), exist_ok=True)
                with open(cmds, 'w') as f:
                    subprocess.run(
                        [pjoin(const.EBD_PATH, 'generate_eapi_cmd_list'), '-b', self._magic],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f'failed to generate list of EAPI {self} banned commands: {str(e)}')

        with open(cmds, 'r') as f:
            return frozenset(line.strip() for line in f)

    def bash_libs(self):
        """Generate internally implemented EAPI specific bash libs required by the ebd."""
        eapi_global_lib = pjoin(const.EBD_PATH, '.generated', 'libs', self._magic, 'global')
        script = pjoin(const.EBD_PATH, 'generate_eapi_lib')
        # skip generation when installing as the install process takes care of it
        if not os.path.exists(script):
            return

        if not os.path.exists(eapi_global_lib):
            try:
                os.makedirs(os.path.dirname(eapi_global_lib), exist_ok=True)
                with open(eapi_global_lib, 'w') as f:
                    subprocess.run(
                        [script, '-s', 'global', self._magic],
                        cwd=const.EBD_PATH, stdout=f)
            except (IOError, subprocess.CalledProcessError) as e:
                raise Exception(
                    f"failed to generate EAPI '{self}' global lib: {str(e)}")

        for phase in self.phases.values():
            eapi_lib = pjoin(const.EBD_PATH, '.generated', 'libs', self._magic, phase)
            if not os.path.exists(eapi_lib):
                try:
                    os.makedirs(os.path.dirname(eapi_lib), exist_ok=True)
                    with open(eapi_lib, 'w') as f:
                        subprocess.run(
                            [script, '-s', phase, self._magic],
                            cwd=const.EBD_PATH, stdout=f)
                except (IOError, subprocess.CalledProcessError) as e:
                    raise Exception(f"failed to generate EAPI '{self}' phase {phase} lib: {str(e)}")

    @klass.jit_attr
    def archive_exts_regex_pattern(self):
        """Regex pattern for supported archive extensions."""
        pattern = '|'.join(map(re.escape, self.archive_exts))
        if self.options.unpack_case_insensitive:
            return f'(?i:({pattern}))'
        return f'({pattern})'

    @klass.jit_attr
    def archive_exts_regex(self):
        """Regex matching strings ending with supported archive extensions."""
        return re.compile(rf'{self.archive_exts_regex_pattern}$')

    @klass.jit_attr
    def valid_slot_regex(self):
        """Regex matching valid SLOT values."""
        valid_slot = r'[A-Za-z0-9_][A-Za-z0-9+_.-]*'
        if self.options.sub_slotting:
            valid_slot += rf'(/{valid_slot})?'
        return re.compile(rf'^{valid_slot}$')

    @klass.jit_attr
    def atom_kls(self):
        return partial(atom.atom, eapi=self._magic)

    def interpret_cache_defined_phases(self, sequence):
        phases = set(sequence)
        if not self.options.trust_defined_phases_cache:
            if not phases:
                # run them all; cache was generated
                # by a pm that didn't support DEFINED_PHASES
                return frozenset(self.phases)

        phases.discard("-")
        return frozenset(phases)

    def __str__(self):
        return self._magic

    @property
    def inherits(self):
        """Yield an EAPI's inheritance tree.

        Note that this assumes a simple, linear inheritance tree.
        """
        yield self
        parent = self._parent
        while parent is not None:
            yield parent
            parent = parent._parent

    @klass.jit_attr
    def helpers(self):
        """Phase to directory mapping for EAPI specific helpers to add to $PATH."""
        paths = defaultdict(list)
        for eapi in self.inherits:
            paths['global'].append(pjoin(const.EBUILD_HELPERS_PATH, 'common'))
            helper_dir = pjoin(const.EBUILD_HELPERS_PATH, eapi._magic)
            for dirpath, dirnames, filenames in os.walk(helper_dir):
                if not filenames:
                    continue
                if dirpath == helper_dir:
                    paths['global'].append(dirpath)
                else:
                    phase = os.path.basename(dirpath)
                    if phase in self.phases_rev:
                        paths[phase].append(dirpath)
                    else:
                        raise ValueError(f'unknown phase: {phase!r}')
        return mappings.ImmutableDict((k, tuple(v)) for k, v in paths.items())

    @klass.jit_attr
    def ebd_env(self):
        """Dictionary of EAPI options passed to the ebd environment."""
        d = {}
        for k in self._ebd_env_options:
            d[f"PKGCORE_{k.upper()}"] = str(getattr(self.options, k)).lower()
        d["PKGCORE_EAPI_INHERITS"] = ' '.join(x._magic for x in self.inherits)
        d["EAPI"] = self._magic
        return mappings.ImmutableDict(d)


def get_eapi(magic, suppress_unsupported=True):
    """Return EAPI object for a given identifier."""
    if _valid_EAPI_regex.match(magic) is None:
        eapi_str = f" {magic!r}" if magic else ''
        raise ValueError(f'invalid EAPI{eapi_str}')
    eapi = EAPI.known_eapis.get(magic)
    if eapi is None and suppress_unsupported:
        eapi = EAPI.unknown_eapis.get(magic)
        if eapi is None:
            eapi = EAPI(magic=magic, optionals={'is_supported': False})
            EAPI.unknown_eapis[eapi._magic] = eapi
    return eapi


def _shorten_phase_name(func_name):
    if func_name.startswith(('src_', 'pkg_')):
        return func_name[4:]
    return func_name


def _mk_phase_func_map(*sequence):
    return {_shorten_phase_name(x): x for x in sequence}


def _combine_dicts(*mappings):
    return {k: v for d in mappings for k, v in d.items()}


# Note that pkg_setup is forced by default since this is how our env setup occurs.
common_default_phases = tuple(
    _shorten_phase_name(x) for x in
    ("pkg_setup", "src_unpack", "src_compile", "src_test", "pkg_nofetch"))

common_phases = (
    "pkg_setup", "pkg_config", "pkg_info", "pkg_nofetch",
    "pkg_prerm", "pkg_postrm", "pkg_preinst", "pkg_postinst",
    "src_unpack", "src_compile", "src_test", "src_install",
)

common_mandatory_metadata_keys = (
    "DESCRIPTION", "HOMEPAGE", "IUSE",
    "KEYWORDS", "LICENSE", "SLOT", "SRC_URI",
)

common_dep_keys = (
    "DEPEND", "RDEPEND", "PDEPEND",
)

common_metadata_keys = (
    "RESTRICT", "PROPERTIES", "DEFINED_PHASES", "INHERIT", "INHERITED", "EAPI",
)

common_eclass_keys = ("S", "RESTRICT", "PROPERTIES", "ECONF_SOURCE")

common_tracked_attributes = (
    "cflags", "cbuild", "chost", "ctarget", "cxxflags", "defined_phases",
    "description", "eapi", "distfiles", "fullslot", "homepage", "inherited",
    "iuse", "keywords", "ldflags", "license", "properties",
    "restrict", "source_repository",
)

common_archive_exts = (
    ".tar",
    ".tar.gz", ".tgz", ".tar.Z", ".tar.z",
    ".tar.bz2", ".tbz2", ".tbz",
    ".zip", ".ZIP", ".jar",
    ".gz", ".Z", ".z",
    ".bz2",
    ".rar", ".RAR",
    ".lha", ".LHa", ".LHA", ".lzh",
    ".a", ".deb",
    ".tar.lzma",
    ".lzma",
    ".7z", ".7Z",
)

# Boolean variables exported to the bash side, e.g. ebuild_phase_func is
# exported as PKGCORE_EBUILD_PHASE_FUNC.
common_env_optionals = (
    "bash_compat", "ebuild_phase_func", "global_failglob",
    "new_reads_stdin", "nonfatal", "nonfatal_die",
    "has_desttree",
)

eapi0 = EAPI.register(
    magic="0",
    parent=None,
    phases=_mk_phase_func_map(*common_phases),
    default_phases=_mk_phase_func_map(*common_default_phases),
    mandatory_keys=common_mandatory_metadata_keys,
    dep_keys=common_dep_keys,
    metadata_keys=common_metadata_keys,
    eclass_keys=common_eclass_keys,
    tracked_attributes=common_tracked_attributes,
    archive_exts=common_archive_exts,
    optionals=eapi_optionals,
    ebd_env_options=common_env_optionals,
)

eapi1 = EAPI.register(
    magic="1",
    parent=eapi0,
    phases=eapi0.phases,
    default_phases=eapi0.default_phases,
    mandatory_keys=eapi0.mandatory_keys,
    dep_keys=eapi0.dep_keys,
    metadata_keys=eapi0.metadata_keys,
    eclass_keys=eapi0.eclass_keys,
    tracked_attributes=eapi0.tracked_attributes,
    archive_exts=eapi0.archive_exts,
    optionals=_combine_dicts(eapi0.options, dict(
        iuse_defaults=True,
    )),
    ebd_env_options=eapi0._ebd_env_options,
)

eapi2 = EAPI.register(
    magic="2",
    parent=eapi1,
    phases=_combine_dicts(
        eapi1.phases, _mk_phase_func_map("src_prepare", "src_configure")),
    default_phases=eapi1.default_phases.union(
        list(map(_shorten_phase_name, ["src_prepare", "src_configure"]))),
    mandatory_keys=eapi1.mandatory_keys,
    dep_keys=eapi1.dep_keys,
    metadata_keys=eapi1.metadata_keys,
    eclass_keys=eapi1.eclass_keys,
    tracked_attributes=eapi1.tracked_attributes,
    archive_exts=eapi1.archive_exts,
    optionals=_combine_dicts(eapi1.options, dict(
        doman_language_detect=True,
        transitive_use_atoms=True,
        src_uri_renames=True,
    )),
    ebd_env_options=eapi1._ebd_env_options,
)

eapi3 = EAPI.register(
    magic="3",
    parent=eapi2,
    phases=eapi2.phases,
    default_phases=eapi2.default_phases,
    mandatory_keys=eapi2.mandatory_keys,
    dep_keys=eapi2.dep_keys,
    metadata_keys=eapi2.metadata_keys,
    eclass_keys=eapi2.eclass_keys | frozenset(['EPREFIX', 'ED', 'EROOT']),
    tracked_attributes=eapi2.tracked_attributes,
    archive_exts=eapi2.archive_exts | frozenset([".tar.xz", ".xz"]),
    optionals=_combine_dicts(eapi2.options, dict(
        prefix_capable=True,
    )),
    ebd_env_options=eapi2._ebd_env_options,
)

eapi4 = EAPI.register(
    magic="4",
    parent=eapi3,
    phases=_combine_dicts(eapi3.phases, _mk_phase_func_map("pkg_pretend")),
    default_phases=eapi3.default_phases.union([_shorten_phase_name('src_install')]),
    mandatory_keys=eapi3.mandatory_keys,
    dep_keys=eapi3.dep_keys,
    metadata_keys=eapi3.metadata_keys | frozenset(["REQUIRED_USE"]),
    eclass_keys=eapi3.eclass_keys | frozenset(["DOCS", "REQUIRED_USE"]),
    tracked_attributes=eapi3.tracked_attributes,
    archive_exts=eapi3.archive_exts,
    optionals=_combine_dicts(eapi3.options, dict(
        dodoc_allow_recursive=True,
        doman_language_override=True,
        nonfatal=False,
        exports_replacing=True,
        has_AA=False, has_KV=False,
        has_merge_type=True,
        has_required_use=True,
        has_use_dep_defaults=True,
        trust_defined_phases_cache=True,
    )),
    ebd_env_options=eapi3._ebd_env_options,
)

eapi5 = EAPI.register(
    magic="5",
    parent=eapi4,
    phases=eapi4.phases,
    default_phases=eapi4.default_phases,
    mandatory_keys=eapi4.mandatory_keys,
    dep_keys=eapi4.dep_keys,
    metadata_keys=eapi4.metadata_keys,
    eclass_keys=eapi4.eclass_keys,
    tracked_attributes=eapi4.tracked_attributes | frozenset(["iuse_effective"]),
    archive_exts=eapi4.archive_exts,
    optionals=_combine_dicts(eapi4.options, dict(
        ebuild_phase_func=True,
        profile_iuse_injection=True,
        profile_stable_use=True,
        query_host_root=True,
        new_reads_stdin=True,
        required_use_one_of=True,
        sub_slotting=True,
    )),
    ebd_env_options=eapi4._ebd_env_options,
)

eapi6 = EAPI.register(
    magic="6",
    parent=eapi5,
    phases=eapi5.phases,
    default_phases=eapi5.default_phases,
    mandatory_keys=eapi5.mandatory_keys,
    dep_keys=eapi5.dep_keys,
    metadata_keys=eapi5.metadata_keys,
    eclass_keys=eapi5.eclass_keys | frozenset(["HTML_DOCS", "PATCHES"]),
    tracked_attributes=eapi5.tracked_attributes | frozenset(["user_patches"]),
    archive_exts=eapi5.archive_exts | frozenset([".txz"]),
    optionals=_combine_dicts(eapi5.options, dict(
        global_failglob=True,
        nonfatal_die=True,
        unpack_absolute_paths=True,
        unpack_case_insensitive=True,
        user_patches=True,
        bash_compat='4.2',
    )),
    ebd_env_options=eapi5._ebd_env_options,
)

eapi7 = EAPI.register(
    magic="7",
    parent=eapi6,
    phases=eapi6.phases,
    default_phases=eapi6.default_phases,
    mandatory_keys=eapi6.mandatory_keys,
    dep_keys=eapi6.dep_keys | frozenset(["BDEPEND"]),
    metadata_keys=eapi6.metadata_keys,
    eclass_keys=eapi6.eclass_keys,
    tracked_attributes=eapi6.tracked_attributes,
    archive_exts=eapi6.archive_exts,
    optionals=_combine_dicts(eapi6.options, dict(
        has_profile_data_dirs=True,
        has_portdir=False,
        has_desttree=False,
        profile_pkg_provided=False,
        query_host_root=False,
        query_deps=True,
        has_sysroot=True,
        has_env_unset=True,
        trailing_slash='',
    )),
    ebd_env_options=eapi6._ebd_env_options,
)
