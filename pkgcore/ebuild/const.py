# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/GPL2

"""
ebuild internal constants
"""

from snakeoil.osutils import pjoin
from pkgcore import const


incrementals = (
    "ACCEPT_KEYWORDS", "ACCEPT_LICENSE", "CONFIG_PROTECT",
    "CONFIG_PROTECT_MASK", "FEATURES", "IUSE_IMPLICIT",
    "PROFILE_ONLY_VARIABLES", "USE", "USE_EXPAND",
    "USE_EXPAND_HIDDEN", "USE_EXPAND_IMPLICIT", "USE_EXPAND_UNPREFIXED",
)

incrementals_unfinalized = ("USE",)

metadata_keys = (
    "DEFINED_PHASES", "DEPEND", "DESCRIPTION", "EAPI", "HOMEPAGE", "INHERITED",
    "IUSE", "KEYWORDS", "LICENSE", "PDEPEND", "PROPERTIES",
    "RDEPEND", "REQUIRED_USE", "RESTRICT", "SLOT", "SRC_URI", "_eclasses_",
)

WORLD_FILE = '/var/lib/portage/world'

EBD_PATH = const._GET_CONST('EBD_PATH', '%(DATA_PATH)s/ebd')
EBUILD_DAEMON_PATH = pjoin(EBD_PATH, "ebuild-daemon.bash")
EBUILD_HELPERS_PATH = pjoin(EBD_PATH, "helpers")

PKGCORE_DEBUG_VARS = ("PKGCORE_DEBUG", "PKGCORE_PERF_DEBUG")
