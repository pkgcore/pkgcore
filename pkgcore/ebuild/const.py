# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


"""
ebuild internal constants
"""

eapi_capable = (0, 1)
unknown_eapi = 2

incrementals = (
    "USE", "FEATURES", "ACCEPT_KEYWORDS", "ACCEPT_LICENSE",
    "CONFIG_PROTECT_MASK", "CONFIG_PROTECT", "PRELINK_PATH",
    "PRELINK_PATH_MASK")

metadata_keys = (
    'DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI', 'RESTRICT', 'HOMEPAGE', 'LICENSE',
    'DESCRIPTION', 'KEYWORDS', 'INHERITED', 'IUSE', 'PDEPEND', 'PROVIDE',
    'EAPI', '_mtime_', '_eclasses_')

ACCEPT_LICENSE = ()
