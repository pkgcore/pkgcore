# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: const.py 2283 2005-11-10 00:35:14Z ferringb $

# note this is lifted out of portage 2.  so... it's held onto for the sake of having stuff we still need,
# but it does need cleanup.

USER_CONFIG_PATH 	= "/etc/portage"
PRIVATE_PATH		= "/var/lib/portage"

try:
	import portage_custom_path

except (ImportError, AttributeError):
	portage_custom_path = None
	print "warning, can't find portage_custom_path.  which means no custom PORTAGE_BASE_PATH"
	print "so... that means you're getting /usr/lib/portage/ as a base , which quite likely isn't what you want"

PORTAGE_BASE_PATH		= getattr(portage_custom_path, "PORTAGE_BASE_PATH", "/usr/lib/portage/")
PORTAGE_BIN_PATH		= getattr(portage_custom_path, "PORTAGE_BIN_PATH", PORTAGE_BASE_PATH+"/bin")
DEFAULT_CONF_FILE		= getattr(portage_custom_path, "DEFAULT_CONF_FILE", USER_CONFIG_PATH+"/config")
CONF_DEFAULTS			= getattr(portage_custom_path, "CONF_DEFAULTS", PORTAGE_BASE_PATH+"/conf_default_types")

#PORTAGE_PYM_PATH		= PORTAGE_BASE_PATH+"/pym"
#PROFILE_PATH			= "/etc/make.profile"
LOCALE_DATA_PATH		= PORTAGE_BASE_PATH+"/locale"

EBUILD_DAEMON_PATH		= PORTAGE_BIN_PATH+"/ebuild-env/ebuild-daemon.sh"

SANDBOX_BINARY			= "/usr/bin/sandbox"

# XXX compatibility hack.  this shouldn't ever hit a stable release.
import os
if not os.path.exists(SANDBOX_BINARY):
	if os.path.exists(PORTAGE_BIN_PATH+"/sandbox"):
		SANDBOX_BINARY=PORTAGE_BIN_PATH+"/sandbox"

DEPSCAN_SH_BINARY		= "/sbin/depscan.sh"
BASH_BINARY				= "/bin/bash"
MOVE_BINARY				= "/bin/mv"
COPY_BINARY				= "/bin/cp"
PRELINK_BINARY			= "/usr/sbin/prelink"
depends_phase_path		= PORTAGE_BIN_PATH+":/bin:/usr/bin"
EBUILD_ENV_PATH			= map(lambda x:PORTAGE_BIN_PATH+"/"+x, ["ebuild-env", "ebuild-helpers"])+["/sbin","/bin","/usr/sbin","/usr/bin"]
EBD_ENV_PATH			= PORTAGE_BIN_PATH+"/ebuild-env"

WORLD_FILE				= PRIVATE_PATH+"/world"
#MAKE_CONF_FILE			= "/etc/make.conf"
#MAKE_DEFAULTS_FILE		= PROFILE_PATH + "/make.defaults"

INVALID_ENV_FILE		= "/etc/spork/is/not/valid/profile.env"
CUSTOM_MIRRORS_FILE		= USER_CONFIG_PATH+"/mirrors"
SANDBOX_PIDS_FILE		= "/tmp/sandboxpids.tmp"

#CONFCACHE_FILE			= CACHE_PATH+"/confcache"
#CONFCACHE_LIST			= CACHE_PATH+"/confcache_files.anydbm"

LIBFAKEROOT_PATH		= "/usr/lib/libfakeroot.so"
FAKEROOT_PATH			= "/usr/bin/fakeroot"

RSYNC_BIN				= "/usr/bin/rsync"
RSYNC_HOST				= "rsync.gentoo.org/gentoo-portage"

CVS_BIN					= "/usr/bin/cvs"
plugins_dir				= "/var/lib/portage/plugins/"
