# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil import mappings, weakrefs, klass
from snakeoil.demandload import demandload

demandload(
    "functools:partial",
    "pkgcore.ebuild:atom",
    "pkgcore.log:logger",
)

eapi_optionals = mappings.ImmutableDict({
    # Controls what version of bash compatibility to force; see PMS.
    "bash_compat": '3.2',

    # Controls whether -r is allowed for dodoc.
    "dodoc_allow_recursive": False,

    # Controls whether doins recurses symlinks.
    "doins_allow_symlinks": False,

    # Controls the language awareness of doman; see PMS.
    "doman_language_detect": False,

    # Controls whether -i18n option is allowed.
    "doman_language_override": False,

    # Controls --disable-silent-rules passing for econf.
    'econf_disable_silent_rules': False,

    # Controls --disable-dependency-tracking passing for econf.
    'econf_disable_dependency_tracking': False,

    # Controls --docdir and --htmldir passing for econf; see PMS.
    'econf_docdir_and_htmldir': False,

    # Controls whether an ebuild_phase function exists for ebuild consumption.
    'ebuild_phase_func': False,

    # Controls whether REPLACING vars are exported to ebuilds; see PMS.
    "exports_replacing": False,

    # Controls of whether failglob is enabled globally; see PMS.
    "global_failglob": False,

    # Controls whether MERGE vars are exported to ebuilds; see PMS.
    "has_merge_type": False,

    # Controls whether REQUIRED_USE is supported, enforcing constraints on
    # allowed use configuration states.
    "has_required_use": False,

    # Controls whether AA env var is exported to ebuilds; this is a flattened
    # listing of each filename in SRC_URI.
    "has_AA": False,

    # Controls whether KV (kernel version; see PMS for details) is exported.
    "has_KV": False,

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
    "prefix_capable": True,

    # Controls whether profile-defined IUSE injection is supported.
    "profile_iuse_injection": False,

    # Controls whether profiles support package.use.stable.* and use.stable.* files.
    "profile_stable_use": False,

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
    "trust_defined_phases_cache": True,

    # Controls whether unpack supports absolute paths; see PMS.
    "unpack_absolute_paths": False,

    # Controls whether unpack supports absolute paths; see PMS.
    "unpack_case_insensitive": False,
})


class _optionals_cls(mappings.ImmutableDict):

    mappings.inject_getitem_as_getattr(locals())


class EAPI(object):

    known_eapis = weakrefs.WeakValCache()
    unknown_eapis = weakrefs.WeakValCache()
    __metaclass__ = klass.immutable_instance

    def __init__(self, magic, parent, phases, default_phases, metadata_keys, mandatory_keys,
                 tracked_attributes, optionals, ebd_env_options=None):
        sf = object.__setattr__

        sf(self, "_magic", str(magic))
        sf(self, "_parent", parent)

        sf(self, "phases", mappings.ImmutableDict(phases))
        sf(self, "phases_rev", mappings.ImmutableDict((v, k) for k, v in
           self.phases.iteritems()))

        # We track the phases that have a default implementation- this is
        # primarily due to DEFINED_PHASES cache values not including it.

        sf(self, "default_phases", frozenset(default_phases))

        sf(self, "mandatory_keys", frozenset(mandatory_keys))
        sf(self, "metadata_keys", frozenset(metadata_keys))
        sf(self, "tracked_attributes", frozenset(tracked_attributes))
        d = dict(eapi_optionals)
        d.update(optionals)
        sf(self, 'options', _optionals_cls(d))
        if ebd_env_options is None:
            ebd_env_options = {}
        sf(self, "ebd_env_options", mappings.ImmutableDict(ebd_env_options))

    @classmethod
    def register(cls, *args, **kwds):
        eapi = cls(*args, **kwds)
        pre_existing = cls.known_eapis.get(eapi._magic)
        if pre_existing is not None:
            raise ValueError(
                "EAPI %s is already known/instantiated- %r" %
                (eapi._magic, pre_existing))
        cls.known_eapis[eapi._magic] = eapi
        return eapi

    @klass.jit_attr
    def is_supported(self):
        """Check if an EAPI is supported."""
        if EAPI.known_eapis.get(self._magic) is not None:
            if not self.options.is_supported:
                logger.warning("EAPI %s isn't fully supported" % self)
            return True
        return False

    @klass.jit_attr
    def atom_kls(self):
        return partial(atom.atom, eapi=int(self._magic))

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

    def get_ebd_env(self):
        """Return EAPI options passed to the ebd environment."""
        d = {}
        for k, converter in self.ebd_env_options.iteritems():
            d["PKGCORE_%s" % (k.upper(),)] = converter(getattr(self.options, k))
        d["EAPI"] = self._magic
        return d


def get_eapi(magic, suppress_unsupported=True):
    """Return EAPI object for a given identifier."""
    eapi = EAPI.known_eapis.get(magic)
    if eapi is None and suppress_unsupported:
        eapi = EAPI.unknown_eapis.get(magic)
        if eapi is None:
            eapi = EAPI(
                magic=magic, parent=None, phases=(), default_phases=(),
                metadata_keys=(), mandatory_keys=(), tracked_attributes=(),
                optionals={'is_supported': False})
            EAPI.unknown_eapis[eapi._magic] = eapi
    return eapi


def _shorten_phase_name(func_name):
    if func_name.startswith(('src_', 'pkg_')):
        return func_name[4:]
    return func_name


def _mk_phase_func_map(*sequence):
    d = {}
    for x in sequence:
        d[_shorten_phase_name(x)] = x
    return d


def _combine_dicts(*sequence_of_mappings):
    d = {}
    for mapping in sequence_of_mappings:
        d.update(mapping)
    return d


# Note that pkg_setup is forced by default since this is how our env setup occurs.
common_default_phases = tuple(
    _shorten_phase_name(x) for x in
    ("pkg_setup", "src_unpack", "src_compile", "src_test", "pkg_nofetch"))

common_phases = (
    "pkg_setup", "pkg_config", "pkg_info", "pkg_nofetch",
    "pkg_prerm", "pkg_postrm", "pkg_preinst", "pkg_postinst",
    "src_unpack", "src_compile", "src_test", "src_install")

common_mandatory_metadata_keys = (
    "DESCRIPTION", "HOMEPAGE", "IUSE",
    "KEYWORDS", "LICENSE", "SLOT", "SRC_URI")

common_metadata_keys = common_mandatory_metadata_keys + (
    "DEPEND", "RDEPEND", "PDEPEND", "RESTRICT",
    "DEFINED_PHASES", "PROPERTIES", "EAPI")

common_tracked_attributes = (
    "cflags", "cbuild", "chost", "ctarget", "cxxflags", "defined_phases",
    "depends", "description", "eapi", "fullslot", "homepage", "inherited",
    "iuse", "keywords", "ldflags", "license", "post_rdepends", "properties",
    "rdepends", "restrict", "source_repository",
)

# Boolean variables exported to the bash side, e.g. ebuild_phase_func is
# exported as PKGCORE_EBUILD_PHASE_FUNC.
common_env_optionals = mappings.ImmutableDict(dict.fromkeys(
    ("bash_compat", "dodoc_allow_recursive", "doins_allow_symlinks",
     "doman_language_detect", "doman_language_override", "ebuild_phase_func",
     "econf_disable_dependency_tracking", "econf_disable_silent_rules",
     "econf_docdir_and_htmldir", "global_failglob",
     "new_reads_stdin", "nonfatal", "nonfatal_die", "profile_iuse_injection",
     "unpack_absolute_paths", "unpack_case_insensitive",),
    lambda s: str(s).lower()))


eapi0 = EAPI.register(
    magic="0",
    parent=None,
    phases=_mk_phase_func_map(*common_phases),
    default_phases=_mk_phase_func_map(*common_default_phases),
    metadata_keys=common_metadata_keys,
    mandatory_keys=common_mandatory_metadata_keys,
    tracked_attributes=common_tracked_attributes,
    optionals=dict(
        trust_defined_phases_cache=False,
        prefix_capable=False,
        has_AA=True,
        has_KV=True,
    ),
    ebd_env_options=common_env_optionals,
)

eapi1 = EAPI.register(
    magic="1",
    parent=eapi0,
    phases=eapi0.phases,
    default_phases=eapi0.default_phases,
    metadata_keys=eapi0.metadata_keys,
    mandatory_keys=eapi0.mandatory_keys,
    tracked_attributes=eapi0.tracked_attributes,
    optionals=_combine_dicts(eapi0.options, dict(
        iuse_defaults=True,
    )),
    ebd_env_options=eapi0.ebd_env_options,
)

eapi2 = EAPI.register(
    magic="2",
    parent=eapi1,
    phases=_combine_dicts(
        eapi1.phases, _mk_phase_func_map("src_prepare", "src_configure")),
    default_phases=eapi1.default_phases.union(
        map(_shorten_phase_name, ["src_prepare", "src_configure"])),
    metadata_keys=eapi1.metadata_keys,
    mandatory_keys=eapi1.mandatory_keys,
    tracked_attributes=eapi1.tracked_attributes,
    optionals=_combine_dicts(eapi1.options, dict(
        doman_language_detect=True,
        transitive_use_atoms=True,
        src_uri_renames=True,
    )),
    ebd_env_options=eapi1.ebd_env_options,
)

eapi3 = EAPI.register(
    magic="3",
    parent=eapi2,
    phases=eapi2.phases,
    default_phases=eapi2.default_phases,
    metadata_keys=eapi2.metadata_keys,
    mandatory_keys=eapi2.mandatory_keys,
    tracked_attributes=eapi2.tracked_attributes,
    optionals=_combine_dicts(eapi2.options, dict(
        prefix_capable=True,
    )),
    ebd_env_options=eapi2.ebd_env_options,
)

eapi4 = EAPI.register(
    magic="4",
    parent=eapi3,
    phases=_combine_dicts(eapi3.phases, _mk_phase_func_map("pkg_pretend")),
    default_phases=eapi3.default_phases.union([_shorten_phase_name('src_install')]),
    metadata_keys=eapi3.metadata_keys | frozenset(["REQUIRED_USE"]),
    mandatory_keys=eapi3.mandatory_keys,
    tracked_attributes=eapi3.tracked_attributes,
    optionals=_combine_dicts(eapi3.options, dict(
        dodoc_allow_recursive=True,
        doins_allow_symlinks=True,
        doman_language_override=True,
        nonfatal=False,
        econf_disable_dependency_tracking=True,
        exports_replacing=True,
        has_AA=False, has_KV=False,
        has_merge_type=True,
        has_required_use=True,
        trust_defined_phases_cache=True,
    )),
    ebd_env_options=eapi3.ebd_env_options,
)

eapi5 = EAPI.register(
    magic="5",
    parent=eapi4,
    phases=eapi4.phases,
    default_phases=eapi4.default_phases,
    metadata_keys=eapi4.metadata_keys,
    mandatory_keys=eapi4.mandatory_keys,
    tracked_attributes=eapi4.tracked_attributes | frozenset(["iuse_effective"]),
    optionals=_combine_dicts(eapi4.options, dict(
        ebuild_phase_func=True,
        econf_disable_silent_rules=True,
        profile_iuse_injection=True,
        profile_stable_use=True,
        new_reads_stdin=True,
        required_use_one_of=True,
        sub_slotting=True,
    )),
    ebd_env_options=eapi4.ebd_env_options,
)

eapi6 = EAPI.register(
    magic="6",
    parent=eapi5,
    phases=eapi5.phases,
    default_phases=eapi5.default_phases,
    metadata_keys=eapi5.metadata_keys,
    mandatory_keys=eapi5.mandatory_keys,
    tracked_attributes=eapi5.tracked_attributes,
    optionals=_combine_dicts(eapi5.options, dict(
        econf_docdir_and_htmldir=True,
        global_failglob=True,
        nonfatal_die=True,
        unpack_absolute_paths=True,
        unpack_case_insensitive=True,
        bash_compat='4.2',
    )),
    ebd_env_options=eapi5.ebd_env_options,
)
