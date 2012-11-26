# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil import mappings, weakrefs, klass
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.ebuild:atom",
    "snakeoil.currying:partial",
)

eapi_optionals = mappings.ImmutableDict({
    "trust_defined_phases_cache":True,
    "prefix_capable":True,
    "has_merge_type":False,
    "exports_replacing":False,
    "dodoc_allow_recursive":False,
    "doins_allow_symlinks":False,
    "doman_language_detect":False,
    "doman_language_override":False,
    "transitive_use_atoms":False,
    "src_uri_renames":False,
    "has_required_use":False,
    "has_AA":False,
    "has_KV":False,
    'is_supported':True,
    'required_use_one_of':False,
    'sub_slotting':False,
    'new_reads_stdin':False,
})


class optionals_cls(mappings.ImmutableDict):

    mappings.inject_getitem_as_getattr(locals())


class EAPI(object):

    known_eapis = weakrefs.WeakValCache()
    __metaclass__ = klass.immutable_instance

    def __init__(self, magic, phases, default_phases, metadata_keys, mandatory_keys,
                 optionals, ebd_env_options=None):

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

    is_supported = klass.alias_attr('options.is_supported')

    @classmethod
    def get_unsupported_eapi(cls, magic):
        return cls(magic, (), (), (), (), {'is_supported':False})

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
    "KEYWORDS",
    "LICENSE", "SLOT", "SRC_URI")

common_metadata_keys = common_mandatory_metadata_keys + (
    "DEPEND", "RDEPEND", "PDEPEND", "PROVIDE", "RESTRICT",
    "DEFINED_PHASES", "PROPERTIES", "EAPI")

common_env_optionals = mappings.ImmutableDict(dict.fromkeys(
    ("dodoc_allow_recursive", "doins_allow_symlinks",
     "doman_language_detect", "doman_language_override"),
        convert_bool_to_bash_bool))


eapi0 = EAPI.register("0",
    mk_phase_func_map(*common_phases),
    mk_phase_func_map(*common_default_phases),
    common_metadata_keys,
    common_mandatory_metadata_keys,
    dict(trust_defined_phases_cache=False, prefix_capable=False, has_AA=True, has_KV=True),
    ebd_env_options=common_env_optionals,
)

eapi1 = EAPI.register("1",
    eapi0.phases,
    eapi0.default_phases,
    eapi0.metadata_keys,
    eapi0.mandatory_keys,
    eapi0.options,
    ebd_env_options=eapi0.ebd_env_options,
)

eapi2 = EAPI.register("2",
    combine_dicts(eapi1.phases, mk_phase_func_map("src_prepare", "src_configure")),
    eapi1.default_phases.union(map(shorten_phase_name, ["src_prepare", "src_configure"])),
    eapi1.metadata_keys,
    eapi1.mandatory_keys,
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
    combine_dicts(eapi2.options,
        dict(prefix_capable=True, has_AA=True, has_KV=True)),
    ebd_env_options=eapi2.ebd_env_options,
)

eapi4 = EAPI.register("4",
    combine_dicts(eapi3.phases, mk_phase_func_map("pkg_pretend")),
    eapi3.default_phases.union([shorten_phase_name('src_install')]),
    eapi3.metadata_keys | frozenset(["REQUIRED_USE"]),
    eapi3.mandatory_keys,
    combine_dicts(eapi3.options, dict(
        trust_defined_phases_cache=True,
        has_merge_type=True,
        exports_replacing=True,
        dodoc_allow_recursive=True,
        doins_allow_recursive=True,
        doman_language_override=True,
        has_required_use=True,
        has_AA=False, has_KV=False,
    )),
    ebd_env_options=eapi3.ebd_env_options,
)


eapi5 = EAPI.register("5",
    eapi4.phases,
    eapi4.default_phases,
    eapi4.metadata_keys,
    eapi4.mandatory_keys,
    combine_dicts(eapi4.options, dict(
        required_use_one_of=True,
        sub_slotting=True,
        new_reads_stdin=True,
        is_supported=False,
    )),
    ebd_env_options=eapi4.ebd_env_options,
)
