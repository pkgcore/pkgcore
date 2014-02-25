# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil import mappings, weakrefs, klass
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.ebuild:atom",
    "pkgcore.log:logger",
    "snakeoil.currying:partial",
)

eapi_optionals = mappings.ImmutableDict({
    # Controls whether -j1 is forced for emake tests
    'allow_parallel_src_test':False,

    # Controls whether -r is allowed for dodoc
    "dodoc_allow_recursive":False,

    # Controls whether doins recurses symlinks
    "doins_allow_symlinks":False,

    # Controls the language awareness of doman; see PMS
    "doman_language_detect":False,

    # Controls whether -i18n option is allowed.
    "doman_language_override":False,

    # Controls --disable-silent-rules passing for econf.
    'econf_disable_silent_rules':False,

    # Controls --disable-dependency-tracking passing for econf.
    'econf_disable_dependency_tracking':False,

    # Controls whether an ebuild_phase function exists for ebuild consumption
    'ebuild_phase_func':False,

    # Controls whether REPLACING vars are exported to ebuilds; see PMS.
    "exports_replacing":False,

    # Controls whether MERGE vars are exported to ebuilds; see PMS.
    "has_merge_type":False,

    # Controls whether REQUIRED_USE is supported, enforcing constraints on
    # allowed use configuration states
    "has_required_use":False,

    # Controls whether AA env var is exported to ebuilds; this is a flattened
    # listing of each filename in SRC_URI
    "has_AA":False,

    # Controls whether KV (kernel version; see PMS for details) is exported
    "has_KV":False,

    # Controls whether or not pkgcore, or extensions loaded, actually fully support
    # this EAPI.
    'is_supported':True,

    # Controls whether new* style bash functions can take their content input from
    # stdin, rather than an explicit ondisk file.
    'new_reads_stdin':False,

    # Controls whether this EAPI supports prefix related variables/settings; prefix
    # awareness basically.  See PMS for full details.
    "prefix_capable":True,

    # Controls whether profile-defined IUSE injection is supported.
    "profile_iuse_injection": False,

    # Controls whether profiles support package.use.stable.* and use.stable.* files.
    "profile_stable_use": False,

    # Controls whether SLOT values can actually be multi-part; see PMS EAPI5.  This is
    # related to ABI breakage detection.
    'sub_slotting':False,

    # Controls whether REQUIRED_USE supports the ?? operator.
    'required_use_one_of':False,

    # Controls whether SRC_URI supports the '->' operator for url filename renaming.
    "src_uri_renames":False,

    # Controls whether or not use dependency atoms are able to control their enforced
    # value relative to another; standard use deps just enforce either on or off; EAPIs
    # supporting this allow syntax that can enforce (for example) X to be on if Y is on.
    # See PMS EAPI4 for full details.
    "transitive_use_atoms":False,

    # Controls whether or DEFINED_PHASES is mandated for this EAPI; if so, then we can
    # trust the cache definition and skip invoking those phases if they're not defined.
    # If the EAPI didn't mandate this var, then we can do our inference, but generally will
    # invoke the phase in the absense of that metadata var since we have no other choice.
    "trust_defined_phases_cache":True,
})


class optionals_cls(mappings.ImmutableDict):

    mappings.inject_getitem_as_getattr(locals())


class EAPI(object):

    known_eapis = weakrefs.WeakValCache()
    __metaclass__ = klass.immutable_instance

    def __init__(self, magic, phases, default_phases, metadata_keys, mandatory_keys,
                 tracked_attributes, optionals, ebd_env_options=None):

        sf = object.__setattr__

        sf(self, "magic", magic)

        sf(self, "phases", mappings.ImmutableDict(phases))
        sf(self, "phases_rev", mappings.ImmutableDict((v, k) for k,v in
            self.phases.iteritems()))

        # we track the phases that have a default implementation-
        # this is primarily due to DEFINED_PHASES cache values
        # not including it.

        sf(self, "default_phases", frozenset(default_phases))

        sf(self, "mandatory_keys", frozenset(mandatory_keys))
        sf(self, "metadata_keys", frozenset(metadata_keys))
        sf(self, "tracked_attributes", frozenset(tracked_attributes))
        d = dict(eapi_optionals)
        d.update(optionals)
        sf(self, 'options', optionals_cls(d))
        if ebd_env_options is None:
            ebd_env_options = {}
        sf(self, "ebd_env_options", mappings.ImmutableDict(ebd_env_options))

    @classmethod
    def register(cls, *args, **kwds):
        ret = cls(*args, **kwds)
        pre_existing = cls.known_eapis.get(ret.magic)
        if pre_existing is not None:
            raise ValueError("eapi magic %s is already known/instantiated- %r" %
                (ret.magic, pre_existing))
        cls.known_eapis[ret.magic] = ret
        return ret

    @klass.jit_attr
    def is_supported(self):
        if EAPI.known_eapis.get(self.magic) is not None:
            if not self.options.is_supported:
                logger.warning("EAPI %s isn't fully supported" % self.magic)
            return True
        return False

    @classmethod
    def get_unsupported_eapi(cls, magic):
        return cls(magic, (), (), (), (), (), {'is_supported':False})

    @klass.jit_attr
    def atom_kls(self):
        return partial(atom.atom, eapi=int(self.magic))

    def interpret_cache_defined_phases(self, sequence):
        phases = set(sequence)
        if not self.options.trust_defined_phases_cache:
            if not phases:
                # run them all; cache was generated
                # by a pm that didn't support DEFINED_PHASES
                return frozenset(self.phases)

        phases.discard("-")
        return frozenset(phases)

    def get_ebd_env(self):
        d = {}
        for k, converter in self.ebd_env_options.iteritems():
            d["PKGCORE_%s" % (k.upper(),)] = converter(getattr(self.options, k))
        d["EAPI"] = str(self.magic)
        return d


def get_eapi(magic, suppress_unsupported=True):
    ret = EAPI.known_eapis.get(magic)
    if ret is None and suppress_unsupported:
        return EAPI.get_unsupported_eapi(magic)
    return ret

def shorten_phase_name(func_name):
    if func_name.startswith("src_") or func_name.startswith("pkg_"):
        return func_name[4:]
    return func_name

def mk_phase_func_map(*sequence):
    d = {}
    for x in sequence:
        d[shorten_phase_name(x)] = x
    return d

def combine_dicts(*sequence_of_mappings):
    d = {}
    for mapping in sequence_of_mappings:
        d.update(mapping)
    return d

def convert_bool_to_bash_bool(val):
    return str(bool(val)).lower()

# Note that pkg_setup is forced by default since this is how our env setup occurs.
common_default_phases = tuple(shorten_phase_name(x)
    for x in ("pkg_setup", "src_unpack", "src_compile", "src_test", "pkg_nofetch"))

common_phases = ("pkg_setup", "pkg_config", "pkg_info", "pkg_nofetch",
    "pkg_prerm", "pkg_postrm", "pkg_preinst", "pkg_postinst",
    "src_unpack", "src_compile", "src_test", "src_install")

common_mandatory_metadata_keys = ("DESCRIPTION", "HOMEPAGE", "IUSE",
    "KEYWORDS", "LICENSE", "SLOT", "SRC_URI")

common_metadata_keys = common_mandatory_metadata_keys + (
    "DEPEND", "RDEPEND", "PDEPEND", "PROVIDE", "RESTRICT",
    "DEFINED_PHASES", "PROPERTIES", "EAPI")

common_tracked_attributes = ("depends", "rdepends", "post_rdepends", "provides",
    "license", "fullslot", "keywords", "eapi_obj", "restrict", "description",
    "iuse", "chost", "cbuild", "ctarget", "homepage", "properties", "inherited",
    "defined_phases", "source_repository")

common_env_optionals = mappings.ImmutableDict(dict.fromkeys(
    ("dodoc_allow_recursive", "doins_allow_symlinks",
     "doman_language_detect", "doman_language_override",
     "econf_disable_silent_rules", "profile_iuse_injection",),
        convert_bool_to_bash_bool))


eapi0 = EAPI.register("0",
    mk_phase_func_map(*common_phases),
    mk_phase_func_map(*common_default_phases),
    common_metadata_keys,
    common_mandatory_metadata_keys,
    common_tracked_attributes,
    dict(trust_defined_phases_cache=False, prefix_capable=False, has_AA=True, has_KV=True),
    ebd_env_options=common_env_optionals,
)

eapi1 = EAPI.register("1",
    eapi0.phases,
    eapi0.default_phases,
    eapi0.metadata_keys,
    eapi0.mandatory_keys,
    eapi0.tracked_attributes,
    eapi0.options,
    ebd_env_options=eapi0.ebd_env_options,
)

eapi2 = EAPI.register("2",
    combine_dicts(eapi1.phases, mk_phase_func_map("src_prepare", "src_configure")),
    eapi1.default_phases.union(map(shorten_phase_name, ["src_prepare", "src_configure"])),
    eapi1.metadata_keys,
    eapi1.mandatory_keys,
    eapi1.tracked_attributes,
    combine_dicts(eapi1.options,
        dict(doman_language_detect=True, transitive_use_atoms=True,
             src_uri_renames=True, has_AA=True, has_KV=True)),
    ebd_env_options=eapi1.ebd_env_options,
)

eapi3 = EAPI.register("3",
    eapi2.phases,
    eapi2.default_phases,
    eapi2.metadata_keys,
    eapi2.mandatory_keys,
    eapi2.tracked_attributes,
    combine_dicts(eapi2.options,
        dict(prefix_capable=True, has_AA=True, has_KV=True)),
    ebd_env_options=eapi2.ebd_env_options,
)

eapi4 = EAPI.register("4",
    combine_dicts(eapi3.phases, mk_phase_func_map("pkg_pretend")),
    eapi3.default_phases.union([shorten_phase_name('src_install')]),
    eapi3.metadata_keys | frozenset(["REQUIRED_USE"]),
    eapi3.mandatory_keys,
    eapi3.tracked_attributes,
    combine_dicts(eapi3.options, dict(
        dodoc_allow_recursive=True,
        doins_allow_symlinks=True,
        doman_language_override=True,
        econf_disable_dependency_tracking=True,
        exports_replacing=True,
        has_AA=False, has_KV=False,
        has_merge_type=True,
        has_required_use=True,
        trust_defined_phases_cache=True,
    )),
    ebd_env_options=eapi3.ebd_env_options,
)

eapi5 = EAPI.register("5",
    eapi4.phases,
    eapi4.default_phases,
    eapi4.metadata_keys,
    eapi4.mandatory_keys,
    eapi4.tracked_attributes | frozenset(["iuse_effective"]),
    combine_dicts(eapi4.options, dict(
        allow_parallel_src_test=True,
        ebuild_phase_func=True,
        econf_disable_silent_rules=True,
        is_supported=False,
        profile_iuse_injection=True,
        profile_stable_use=True,
        new_reads_stdin=True,
        required_use_one_of=True,
        sub_slotting=True,
    )),
    ebd_env_options=eapi4.ebd_env_options,
)
