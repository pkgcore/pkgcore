# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/GPL2


"""
ebuild internal constants
"""
from os import path

eapi_capable = (0, 1, 2, 3)

incrementals = (
    "USE", "FEATURES", "ACCEPT_KEYWORDS", "ACCEPT_LICENSE",
    "CONFIG_PROTECT_MASK", "CONFIG_PROTECT", "PRELINK_PATH",
    "PRELINK_PATH_MASK")

incrementals_unfinalized = ("USE",)

metadata_keys = (
    'DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI', 'RESTRICT', 'HOMEPAGE', 'LICENSE',
    'DESCRIPTION', 'KEYWORDS', 'INHERITED', 'IUSE', 'PDEPEND', 'PROVIDE',
    'EAPI', 'PROPERTIES', 'DEFINED_PHASES', '_mtime_', '_eclasses_')

ACCEPT_LICENSE = ()

EAPI_BIN_PATH        = path.join(path.dirname(path.abspath(__file__)), "eapi-bash")
EBUILD_DAEMON_PATH   = path.join(EAPI_BIN_PATH, "ebuild-daemon.bash")
EBUILD_HELPERS_PATH  = path.join(EAPI_BIN_PATH, "helpers")
EBD_ENV_PATH         = EAPI_BIN_PATH
