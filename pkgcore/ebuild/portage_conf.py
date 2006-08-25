# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
make.conf translator, converts portage configuration files into L{pkgcore.config} form
"""

import os
from pkgcore.config import basics, introspect
from pkgcore import const
from pkgcore.util.modules import load_attribute
from pkgcore.util.demandload import demandload
demandload(globals(), "errno pkgcore.config:errors " +
	"pkgcore.pkgsets.glsa:SecurityUpgrades "+
	"pkgcore.fs.util:normpath,abspath "+
	"pkgcore.util.file:read_bash_dict,read_dict "+
	"pkgcore.pkgsets.filelist:FileList "+
	"pkgcore.util.osutils:listdir_files ")


def SecurityUpgradesViaProfile(ebuild_repo, vdb, profile):
	"""
	generate a GLSA vuln. pkgset limited by profile
	
	@param ebuild_repo: L{pkgcore.ebuild.repository.UnconfiguredTree} instance
	@param vdb: L{pkgcore.repository.prototype.tree} instance that is the livefs
	@param profile: L{pkgcore.ebuild.profiles} instance
	"""
	arch = profile.conf.get("ARCH")
	if arch is None:
		raise errors.InstantiationError("pkgcore.ebuild.portage_conf.SecurityUpgradesViaProfile", 
			(repo, vdb, profile), {}, "arch wasn't set in profiles")
	return SecurityUpgrades(ebuild_repo, vdb, arch)

SecurityUpgradesViaProfile.pkgcore_config_type = introspect.ConfigHint(types={
	"ebuild_repo":"section_ref", "vdb":"section_ref", "profile":"section_ref"})


def configFromMakeConf(location="/etc/"):
	"""
	generate a config from a file location
	
	@param location: location the portage configuration is based in, defaults to /etc
	"""
	
	# this actually differs from portage parsing- we allow make.globals to provide vars used in make.conf, 
	# portage keeps them seperate (kind of annoying)

	pjoin = os.path.join

	config_root = os.environ.get("CONFIG_ROOT", "/") + "/"
	base_path = pjoin(config_root, location.strip("/"))
	portage_base = pjoin(base_path, "portage")

	# this isn't preserving incremental behaviour for features/use unfortunately
	conf_dict = read_bash_dict(pjoin(base_path, "make.globals"))
	conf_dict.update(read_bash_dict(pjoin(base_path, "make.conf"), vars_dict=conf_dict, sourcing_command="source"))
	conf_dict.setdefault("PORTDIR", "/usr/portage")
	root = os.environ.get("ROOT", conf_dict.get("ROOT", "/"))
	gentoo_mirrors = [x+"/distfiles" for x in conf_dict.pop("GENTOO_MIRRORS", "").split()]
	if not gentoo_mirrors:
		gentoo_mirrors = None

	new_config = {}

	# sets...
	new_config["world"] = basics.ConfigSectionFromStringDict("world", 
		{"type": "pkgset", "class": "pkgcore.pkgsets.filelist.FileList", 
		"location": "%s/%s" % (root, const.WORLD_FILE)})
	new_config["system"] = basics.ConfigSectionFromStringDict("system",
		{"type": "pkgset", "class": "pkgcore.pkgsets.system.SystemSet", 
		"profile": "profile"})

	set_fp = pjoin(portage_base, "sets")
	if os.path.isdir(set_fp):
		for setname in listdir_files(set_fp):
			new_config[setname] = basics.ConfigSectionFromStringDict(setname,
				{"class":"pkgcore.pkgsets.filelist.FileList", "type":"pkgset",
				"location":pjoin(set_fp, setname)})



	new_config["vdb"] = basics.ConfigSectionFromStringDict("vdb",
		{"type": "repo", "class": "pkgcore.vdb.repository", "location": "%s/var/db/pkg" % config_root.rstrip("/")})
	
	try:
		profile = os.readlink(pjoin(base_path, "make.profile"))
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
		"base_path": pjoin("/", *psplit[:stop+1]), "profile": pjoin(*psplit[stop + 1:])})

	portdir = normpath(conf_dict.pop("PORTDIR").strip())
	portdir_overlays = map(normpath, conf_dict.pop("PORTDIR_OVERLAY", "").split())

	cache_config = {"type": "cache", "location": "%s/var/cache/edb/dep" % config_root.rstrip("/"), "label": "make_conf_overlay_cache"}
	pcache = None
	if os.path.exists(base_path+"portage/modules"):
		pcache = read_dict(base_path+"portage/modules").get("portdbapi.auxdbmodule", None)
	
	features = conf_dict.get("FEATURES", "").split()
	
	rsync_portdir_cache = os.path.exists(pjoin(portdir, "metadata", "cache"))
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
	distdir = normpath(conf_dict.pop("DISTDIR", pjoin(portdir, "distdir")))
	fetchcommand = conf_dict.pop("FETCHCOMMAND")
	resumecommand = conf_dict.pop("RESUMECOMMAND", fetchcommand)

	new_config["fetcher"] = basics.ConfigSectionFromStringDict("fetcher", 
		{"type": "fetcher", "distdir": distdir, "command": fetchcommand,
		"resume_command": resumecommand})

	ebuild_repo_class = load_attribute("pkgcore.ebuild.repository.tree")
	
	for tree_loc in [portdir] + portdir_overlays:
		d2 = {"type": "repo", "class": ebuild_repo_class}
		d2["location"] = tree_loc
		d2["cache"] = "%s cache" % tree_loc
		d2["default_mirrors"] = gentoo_mirrors
		new_config[tree_loc] = basics.HardCodedConfigSection(tree_loc, d2)
		if rsync_portdir_cache and tree_loc == portdir:
			c = {"type": "cache", "location": tree_loc, "label": tree_loc, 
				"class": "pkgcore.cache.metadata.database"}
		else:
			c = {"type": "cache", "location": "%s/var/cache/edb/dep" % config_root.rstrip("/"), "label": tree_loc,
				"class": "pkgcore.cache.flat_hash.database"}
		new_config["%s cache" % tree_loc] = \
			basics.ConfigSectionFromStringDict("%s cache" % tree_loc, c)

	if portdir_overlays:
		d = {"type": "repo", "class": load_attribute("pkgcore.ebuild.overlay_repository.OverlayRepo"),
			"default_mirrors":gentoo_mirrors, "cache": "cache", "trees": [portdir] + portdir_overlays}
		# sucky.  needed?
		new_config["portdir"] = basics.HardCodedConfigSection("portdir", d)
	else:
		new_config["portdir"] = new_config[portdir]

	new_config["glsa"] = basics.HardCodedConfigSection("glsa",
		{"type": "pkgset", "class": SecurityUpgradesViaProfile,
		"ebuild_repo": "portdir", "vdb": "vdb", "profile":"profile"})

	#binpkg.
	pkgdir = conf_dict.pop("PKGDIR", None)
	default_repos = "portdir"
	if pkgdir is not None:
		pkgdir = abspath(pkgdir)
		if os.path.isdir(pkgdir):
			new_config["binpkg"] = basics.ConfigSectionFromStringDict("binpkg", 
				{"class":"pkgcore.binpkg.repository.tree", "type":"repo",
				"location":pkgdir})
			default_repos += " binpkg"


	# finally... domain.

	d = {"repositories":default_repos, "fetcher": "fetcher", "default": "yes", 
		"vdb": "vdb", "profile": "profile", "type": "domain"}
	conf_dict.update({"repositories": default_repos, "fetcher": "fetcher", "default": "yes", 
		"vdb": "vdb", "profile": "profile", "type": "domain"})

	# finally... package.* additions
	for f in ("package.mask", "package.unmask", "package.keywords", "package.use"):
		fp = pjoin(portage_base, f)
		if os.path.isfile(fp):
			conf_dict[f] = fp
	new_config["livefs domain"] = basics.ConfigSectionFromStringDict("livefs domain",
		conf_dict)

	return new_config
