# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.config import basics, errors
from pkgcore.util.file import read_bash_dict, read_dict
from pkgcore import const
import os, errno

def configFromMakeConf(location="/etc/"):
	# this actually differs from portage parsing- we allow make.globals to provide vars used in make.conf, 
	# portage keeps them seperate (kind of annoying)

	config_root = os.environ.get("CONFIG_ROOT", "/") + "/"
	base_path = os.path.join(config_root, location.strip("/"))
	make_globals = os.path.join(base_path, "make.globals")
	make_conf = os.path.join(base_path, "make.conf")

	# this isn't preserving incremental behaviour for features/use unfortunately
	conf_dict = read_bash_dict(config_root + make_globals)
	conf_dict.update(read_bash_dict(config_root + make_conf, vars_dict=conf_dict))
	conf_dict.setdefault("PORTDIR", "/usr/portage")
	root = os.environ.get("ROOT", conf_dict.get("ROOT", "/"))

	new_config = {}
	new_config["world"] = basics.ConfigSectionFromStringDict("world", 
		{"type": "pkgset", "class": "pkgcore.pkgsets.world.WorldFile", 
		"world_path": "%s/%s" % (root, const.WORLD_FILE)})
	new_config["system"] = basics.ConfigSectionFromStringDict("system",
		{"type": "pkgset", "class": "pkgcore.pkgsets.system.SystemSet", 
		"profile": "profile"})

	new_config["vdb"] = basics.ConfigSectionFromStringDict("vdb",
		{"type": "repo", "class": "pkgcore.vdb.repository", "location": "%s/var/db/pkg" % config_root.rstrip("/")})
	
	try:
		profile = os.readlink(os.path.join(base_path, "make.profile"))
	except OSError, oe:
		if oe.errno in (errno.ENOENT, errno.EINVAL):
			raise errors.InstantiationError("configFromMakeConf", [], {},
				"%s/make.profile must be a symlink pointing to a real target" % base_path)
		raise errors.InstantiationError("configFromMakeConf", [], {},
			"%s/make.profile: unexepect error- %s" % (base_path, oe))
	psplit = filter(None, profile.split("/"))
	# poor mans rindex.
	try:
		stop = max(idx for idx, val in enumerate(psplit) if val == "profiles")
		if stop + 1 >= len(psplit):
			raise ValueError
	except ValueError, v:
		raise errors.InstantiationError("configFromMakeConf", [], {}, 
			"%s/make.profile expands to %s, but no profile/profile base detected" % (base_path, profile))
	
	new_config["profile"] = basics.ConfigSectionFromStringDict("profile", 
		{"type": "profile", "class": "pkgcore.ebuild.profiles.OnDiskProfile", 
		"base_path": os.path.join("/", *psplit[:stop+1]), "profile": os.path.join(*psplit[stop + 1:])})

	portdir = conf_dict.pop("PORTDIR").strip()
	portdir_overlays = conf_dict.pop("PORTDIR_OVERLAY", "").split()

	cache_config = {"type": "cache", "location": "%s/var/cache/edb/dep" % config_root, "label": "make_conf_overlay_cache"}
	pcache = None
	if os.path.exists(config_root+"portage/modules"):
		pcache = read_dict(config_root+"portage/modules").get("portdbapi.auxdbmodule", None)
	
	features = conf_dict.get("FEATURES", "").split()
	
	rsync_portdir_cache = os.path.exists(os.path.join(portdir, "metadata", "cache"))
	if pcache is None:
		if portdir_overlays or ("metadata-transfer" not in features):
			cache_config["class"] = "pkgcore.cache.flat_hash.database"
		else:
			cache_config["class"] = "pkgcore.cache.metadata.database"
			cache_config["location"] = portdir
			cache_config["readonly"] = "true"			
	else:
		cache_config["class"] = pcache

	new_config["cache"] = basics.ConfigSectionFromStringDict("cache", cache_config)

	#fetcher.
	distdir = conf_dict.pop("DISTDIR", os.path.join(portdir, "distdir"))
	fetchcommand = conf_dict.pop("FETCHCOMMAND")
	resumecommand = conf_dict.pop("RESUMECOMMAND", fetchcommand)

	new_config["fetcher"] = basics.ConfigSectionFromStringDict("fetcher", 
		{"type": "fetcher", "distdir": distdir, "command": fetchcommand,
		"resume_command": resumecommand})

	from pkgcore.util.modules import load_attribute
	ebuild_repo_class = load_attribute("pkgcore.ebuild.repository")
	
	for tree_loc in [portdir] + portdir_overlays:
		d2 = {"type": "repo", "class": ebuild_repo_class}
		d2["location"] = tree_loc
		d2["cache"] = "%s cache" % tree_loc
		new_config[tree_loc] = basics.HardCodedConfigSection(tree_loc, d2)
		if rsync_portdir_cache and tree_loc == portdir:
			c = {"type": "cache", "location": tree_loc, "label": "%s cache" % tree_loc, 
				"class": "pkgcore.cache.metadata.database"}
		else:
			c = {"type": "cache", "location": "%s/var/cache/edb/dep" % config_root, "label": "%s cache" % tree_loc,
				"class": "pkgcore.cache.flat_hash.database"}
		new_config["%s cache" % tree_loc] = \
			basics.ConfigSectionFromStringDict("%s cache" % tree_loc, c)

	if portdir_overlays:
		d = {"type": "repo", "class": load_attribute("pkgcore.ebuild.overlay_repository.OverlayRepo"),
			"cache": "cache", "trees": [portdir] + portdir_overlays}
		# sucky.  needed?
		new_config["portdir"] = basics.HardCodedConfigSection("portdir", d)
	else:
		new_config["portdir"] = new_config[portdir]

	new_config["glsa"] = basics.ConfigSectionFromStringDict("glsa",
		{"type": "pkgset", "class": "pkgcore.pkgsets.glsa.SecurityUpgrades",
		"ebuild_repo": "portdir", "vdb": "vdb"})
	
	# finally... domain.
	d = {"repositories": "portdir", "fetcher": "fetcher", "default": "yes", 
		"vdb": "vdb", "profile": "profile", "type": "domain"}
	conf_dict.update({"repositories": "portdir", "fetcher": "fetcher", "default": "yes", 
		"vdb": "vdb", "profile": "profile", "type": "domain"})

	new_config["livefs domain"] = basics.ConfigSectionFromStringDict("livefs domain",
		conf_dict)

	return new_config		
