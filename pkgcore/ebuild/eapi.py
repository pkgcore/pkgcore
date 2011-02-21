# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil import mappings, weakrefs, klass
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.ebuild:atom",
    "snakeoil.currying:partial",
)

class EAPI(object):

    known_eapis = weakrefs.WeakValCache()

    def __init__(self, magic, phases, default_phases,
        metadata_keys, mandatory_keys,
        trust_defined_phases_cache=True):

        sf = object.__setattr__

        pre_existing = self.known_eapis.get(magic)
        if pre_existing is not None:
            raise ValueError("eapi magic %s is already known/instantiated- %r" %
                (magic, pre_existing))
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
        sf(self, "_trust_defined_phases_cache", trust_defined_phases_cache)
        self.known_eapis[magic] = self

    def __setattr__(self, attr):
        raise AttributeError("instance %r is immutable- tried setting attr %r"
            % (self, attr))

    def __delattr__(self, attr):
        raise AttributeError("instance %r is immutable- tried deleting attr %r"
            % (self, attr))

    @klass.jit_attr
    def atom_kls(self):
        return partial(atom.atom, eapi=int(self.magic))

    def interpret_cache_defined_phases(self, sequence):
        phases = set(sequence)
        if not self._trust_defined_phases_cache:
            if not phases:
                # run them all; cache was generated
                # by a pm that didn't support DEFINED_PHASES
                return frozenset(self.phases)

        phases.discard("-")
        if phases:
            return self.default_phases | phases
        return self.default_phases

def get_eapi(magic):
    return EAPI.known_eapis.get(magic)


def shorten_phase_name(func_name):
    if func_name.startswith("src_") or func_name.startswith("pkg_"):
        return func_name[4:]
    return func_name

def mk_phase_func_map(sequence):
    d = {}
    for x in sequence:
        d[shorten_phase_name(x)] = x
    return d

common_default_phases = tuple(shorten_phase_name(x)
    for x in ("src_unpack", "src_compile", "src_test", "pkg_nofetch"))

common_phases = ("pkg_setup", "pkg_config", "pkg_info", "pkg_nofetch",
    "pkg_prerm", "pkg_postrm", "pkg_preinst", "pkg_postinst",
    "src_unpack", "src_compile", "src_test", "src_install")

common_mandatory_metadata_keys = ("DESCRIPTION", "HOMEPAGE", "IUSE",
    "KEYWORDS",
    "LICENSE", "SLOT", "SRC_URI")

common_metadata_keys = common_mandatory_metadata_keys + (
    "DEPEND", "RDEPEND", "PDEPEND", "PROVIDE", "RESTRICT",
    "DEFINED_PHASES", "PROPERTIES", "EAPI")

eapi0 = EAPI("0",
    mk_phase_func_map(common_phases),
    common_default_phases,
    common_metadata_keys,
    common_mandatory_metadata_keys,
    trust_defined_phases_cache=False)

eapi1 = EAPI("1",
    eapi0.phases,
    eapi0.default_phases,
    eapi0.metadata_keys,
    eapi0.mandatory_keys,
    trust_defined_phases_cache=False)

d = dict(eapi1.phases.iteritems())
d.update(mk_phase_func_map(["src_prepare", "src_configure"]))

eapi2 = EAPI("2",
    d,
    eapi1.default_phases | frozenset(["src_prepare", "src_configure"]),
    eapi1.metadata_keys,
    eapi1.mandatory_keys,
    trust_defined_phases_cache=False)
del d

eapi3 = EAPI("3",
    eapi2.phases,
    eapi2.default_phases,
    eapi2.metadata_keys,
    eapi2.mandatory_keys,
    trust_defined_phases_cache=False)

