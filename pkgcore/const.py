# Copyright: 2005-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


"""
Internal constants.
"""

import os.path as osp


# the pkgcore package directory
PKGCORE_BASE_PATH   = osp.dirname(osp.abspath(__file__))
PKGCORE_BIN_PATH    = osp.join(PKGCORE_BASE_PATH, 'bin')
SYSTEM_CONF_FILE    = '/etc/pkgcore.conf'
USER_CONF_FILE      = osp.expanduser('~/.pkgcore.conf')

EBUILD_DAEMON_PATH  = PKGCORE_BIN_PATH+"/ebuild-env/ebuild-daemon.sh"
SANDBOX_BINARY      = "/usr/bin/sandbox"

# should lift these from configuration, or PATH inspection.
BASH_BINARY          = "/bin/bash"
COPY_BINARY          = "/bin/cp"
PRELINK_BINARY       = "/usr/sbin/prelink"

depends_phase_path   = PKGCORE_BIN_PATH+"/ebuild-env/:/bin:/usr/bin"
EBUILD_ENV_PATH      = [PKGCORE_BIN_PATH+"/"+x for x in [
                           "ebuild-env", "ebuild-helpers"]] \
                     + ["/sbin", "/bin", "/usr/sbin", "/usr/bin"]
EBD_ENV_PATH         = PKGCORE_BIN_PATH+"/ebuild-env"

# XXX this is out of place
WORLD_FILE           = '/var/lib/portage/world'

# no longer used.
LIBFAKEROOT_PATH     = "/usr/lib/libfakeroot.so"
FAKED_PATH           = "/usr/bin/faked"

VERSION              = '0.5.9'
