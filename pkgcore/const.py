# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


"""
Internal constants.
"""

import os.path as osp


# the pkgcore package directory
PKGCORE_BASE_PATH   = osp.dirname(osp.abspath(__file__))
SYSTEM_CONF_FILE    = '/etc/pkgcore.conf'
USER_CONF_FILE      = osp.expanduser('~/.pkgcore.conf')

SANDBOX_BINARY      = "/usr/bin/sandbox"

# should lift these from configuration, or PATH inspection.
BASH_BINARY          = "/bin/bash"
COPY_BINARY          = "/bin/cp"
PRELINK_BINARY       = "/usr/sbin/prelink"

HOST_NONROOT_PATHS   = ("/usr/bin", "/bin")
HOST_ROOT_PATHS      = ("/usr/sbin", "/usr/bin", "/sbin", "/bin")

# no longer used.
LIBFAKEROOT_PATH     = "/usr/lib/libfakeroot.so"
FAKED_PATH           = "/usr/bin/faked"

VERSION              = '0.6.2'
