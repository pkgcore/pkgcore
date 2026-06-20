"""
ebuild internal constants
"""

from os.path import join as pjoin

from ..const import EBD_PATH

incrementals_unfinalized = ("USE",)

metadata_keys = (
    "BDEPEND",
    "DEPEND",
    "RDEPEND",
    "PDEPEND",
    "IDEPEND",
    "DEFINED_PHASES",
    "DESCRIPTION",
    "EAPI",
    "HOMEPAGE",
    "INHERIT",
    "INHERITED",
    "IUSE",
    "KEYWORDS",
    "LICENSE",
    "PROPERTIES",
    "REQUIRED_USE",
    "RESTRICT",
    "SLOT",
    "SRC_URI",
    "_eclasses_",
)

# EAPI 9 stops exporting PMS-defined and special profile variables to the ebuild
# environment (they remain as plain, unexported shell variables); see PMS and.

# PMS-defined variables that pkgcore injects into the ebuild environment.
PMS_DEFINED_VARS = frozenset(
    {
        "P",
        "PF",
        "PN",
        "PV",
        "PR",
        "PVR",
        "CATEGORY",
        "A",
        "AA",
        "KV",
        "EBUILD",
        "EBUILD_PHASE",
        "EBUILD_PHASE_FUNC",
        "WORKDIR",
        "S",
        "T",
        "D",
        "ED",
        "ROOT",
        "EROOT",
        "EPREFIX",
        "FILESDIR",
        "DISTDIR",
        "PORTDIR",
        "ECLASSDIR",
        "DESTTREE",
        "INSDESTTREE",
        "MERGE_TYPE",
        "REPLACING_VERSIONS",
        "REPLACED_BY_VERSION",
        "USE",
        "SLOT",
        "INHERITED",
        "DEFINED_PHASES",
    }
)

# Special profile variables (those with specific meanings in profiles, see PMS).
# Note: ABI, DEFAULT_ABI and LIBDIR_* are *not* special and remain exported.
SPECIAL_PROFILE_VARS = frozenset(
    {
        "ARCH",
        "CONFIG_PROTECT",
        "CONFIG_PROTECT_MASK",
        "USE",
        "USE_EXPAND",
        "USE_EXPAND_UNPREFIXED",
        "USE_EXPAND_HIDDEN",
        "USE_EXPAND_IMPLICIT",
        "IUSE_IMPLICIT",
        "ENV_UNSET",
        "CHOST",
        "CBUILD",
        "CTARGET",
    }
)

# Variables that are always exported, even in EAPIs that otherwise don't export
# PMS variables (SYSROOT/ESYSROOT/BROOT for cross-compilation, see bug 977170).
ALWAYS_EXPORTED_VARS = frozenset({"HOME", "TMPDIR", "SYSROOT", "ESYSROOT", "BROOT"})

# PMS variables that pkgcore's own external helpers (prepstrip, prepalldocs,
# fperms, ...) read from the environment; kept exported as the PMS-sanctioned
# "implementation-defined manner" of passing them to ebuild-specific commands.
HELPER_EXPORTED_VARS = frozenset({"CATEGORY", "PF", "D", "ED", "T", "WORKDIR"})

WORLD_FILE = "/var/lib/portage/world"

EBUILD_DAEMON_PATH = pjoin(EBD_PATH, "ebuild-daemon.bash")
EBUILD_HELPERS_PATH = pjoin(EBD_PATH, "helpers")

PKGCORE_DEBUG_VARS = ("PKGCORE_DEBUG", "PKGCORE_PERF_DEBUG")
