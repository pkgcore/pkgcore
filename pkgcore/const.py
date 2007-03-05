# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2000-2005 Gentoo Foundation
# License: GPL2


"""
Internal constants.

Future of this module is debatable- for the most part you likely don't
want to be using this. As soon as is possible, most of these defines
will be shifted to wherever they're best situated.
"""

# note this is lifted out of portage 2. so... it's held onto for the
# sake of having stuff we still need, but it does need cleanup.

import os.path as osp


# the pkgcore package directory
PORTAGE_BASE_PATH   = osp.dirname(osp.abspath(__file__))
PKGCORE_BIN_PATH    = osp.join(PORTAGE_BASE_PATH, 'bin')
SYSTEM_CONF_FILE    = '/etc/pkgcore.conf'
USER_CONF_FILE      = osp.expanduser('~/.pkgcore.conf')

#PORTAGE_PYM_PATH   = PORTAGE_BASE_PATH+"/pym"
#PROFILE_PATH       = "/etc/make.profile"
LOCALE_DATA_PATH    = PORTAGE_BASE_PATH+"/locale"

EBUILD_DAEMON_PATH  = PKGCORE_BIN_PATH+"/ebuild-env/ebuild-daemon.sh"

SANDBOX_BINARY      = "/usr/bin/sandbox"

DEPSCAN_SH_BINARY    = "/sbin/depscan.sh"
BASH_BINARY          = "/bin/bash"
MOVE_BINARY          = "/bin/mv"
COPY_BINARY          = "/bin/cp"
PRELINK_BINARY       = "/usr/sbin/prelink"
depends_phase_path   = PKGCORE_BIN_PATH+"/ebuild-env/:/bin:/usr/bin"
EBUILD_ENV_PATH      = [PKGCORE_BIN_PATH+"/"+x for x in [
                           "ebuild-env", "ebuild-helpers"]] \
                     + ["/sbin", "/bin", "/usr/sbin", "/usr/bin"]
EBD_ENV_PATH         = PKGCORE_BIN_PATH+"/ebuild-env"

# XXX this is out of place
WORLD_FILE           = '/var/lib/portage/world'
#MAKE_CONF_FILE       = "/etc/make.conf"
#MAKE_DEFAULTS_FILE   = PROFILE_PATH + "/make.defaults"

# XXX this is out of place
CUSTOM_MIRRORS_FILE  = "/etc/portage/mirrors"
SANDBOX_PIDS_FILE    = "/tmp/sandboxpids.tmp"

#CONFCACHE_FILE       = CACHE_PATH+"/confcache"
#CONFCACHE_LIST       = CACHE_PATH+"/confcache_files.anydbm"

LIBFAKEROOT_PATH     = "/usr/lib/libfakeroot.so"
FAKED_PATH           = "/usr/bin/faked"

RSYNC_BIN            = "/usr/bin/rsync"
RSYNC_HOST           = "rsync.gentoo.org/gentoo-portage"

CVS_BIN              = "/usr/bin/cvs"

VERSION              = '0.2.8'
