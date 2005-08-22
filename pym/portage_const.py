# portage: Constants
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
cvs_id_string="$Id: portage_const.py 1743 2005-04-29 04:43:19Z vapier $"[5:-2]

# ===========================================================================
# START OF CONSTANTS -- START OF CONSTANTS -- START OF CONSTANTS -- START OF
# ===========================================================================

VDB_PATH                = "var/db/pkg"
PRIVATE_PATH            = "/var/lib/portage"
CACHE_PATH              = "/var/cache/edb"
DEPCACHE_PATH           = CACHE_PATH+"/dep"

USER_CONFIG_PATH        = "/etc/portage"
MODULES_FILE_PATH       = USER_CONFIG_PATH+"/modules"
CUSTOM_PROFILE_PATH     = USER_CONFIG_PATH+"/profile"

PORTAGE_BASE_PATH       = "/usr/lib/portage"
PORTAGE_BIN_PATH        = PORTAGE_BASE_PATH+"/bin"
PORTAGE_PYM_PATH        = PORTAGE_BASE_PATH+"/pym"
PROFILE_PATH            = "/etc/make.profile"
LOCALE_DATA_PATH        = PORTAGE_BASE_PATH+"/locale"

EBUILD_SH_BINARY        = PORTAGE_BIN_PATH+"/ebuild.sh"
EBUILD_DAEMON_PATH      = PORTAGE_BIN_PATH+"/ebuild-daemon.sh"

SANDBOX_BINARY          = "/usr/bin/sandbox"
# XXX compatibility hack.  this shouldn't ever hit a stable release.
import os
if not os.path.exists(SANDBOX_BINARY):
	if os.path.exists(PORTAGE_BIN_PATH+"/sandbox"):
		SANDBOX_BINARY=PORTAGE_BIN_PATH+"/sandbox"

BASH_BINARY             = "/bin/bash"
MOVE_BINARY             = "/bin/mv"
PRELINK_BINARY          = "/usr/sbin/prelink"

WORLD_FILE              = PRIVATE_PATH+"/world"
MAKE_CONF_FILE          = "/etc/make.conf"
MAKE_DEFAULTS_FILE      = PROFILE_PATH + "/make.defaults"
DEPRECATED_PROFILE_FILE = PROFILE_PATH+"/deprecated"
USER_VIRTUALS_FILE      = USER_CONFIG_PATH+"/virtuals"
EBUILD_SH_ENV_FILE      = USER_CONFIG_PATH+"/bashrc"
INVALID_ENV_FILE        = "/etc/spork/is/not/valid/profile.env"
CUSTOM_MIRRORS_FILE     = USER_CONFIG_PATH+"/mirrors"
SANDBOX_PIDS_FILE       = "/tmp/sandboxpids.tmp"
CONFIG_MEMORY_FILE      = PRIVATE_PATH + "/config"

INCREMENTALS=["USE","FEATURES","ACCEPT_KEYWORDS","ACCEPT_LICENSE","CONFIG_PROTECT_MASK","CONFIG_PROTECT","PRELINK_PATH","PRELINK_PATH_MASK"]
STICKIES=["KEYWORDS_ACCEPT","USE","CFLAGS","CXXFLAGS","MAKEOPTS","EXTRA_ECONF","EXTRA_EINSTALL","EXTRA_EMAKE"]

CONFCACHE_FILE          = CACHE_PATH+"/confcache"
CONFCACHE_LIST          = CACHE_PATH+"/confcache_files.anydbm"

LIBFAKEROOT_PATH        = "/usr/lib/libfakeroot.so"
FAKEROOT_PATH           = "/usr/bin/fakeroot"

RSYNC_BIN               = "/usr/bin/rsync"
RSYNC_HOST              = "rsync.gentoo.org/gentoo-portage"

CVS_BIN                 = "/usr/bin/cvs"

EBUILD_PHASES			= "setup unpack compile test install preinst postinst prerm postrm"
