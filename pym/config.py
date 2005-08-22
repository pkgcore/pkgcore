import os, copy, re
import portage_const
import sys #has a few daft sys.exit

import portage_util, portage_versions, portage_dep
from portage_util import getconfig, grabfile, grab_multiple, grabfile_package, grabdict, writemsg, grabdict_package, \
	abssymlink, flatten


from portage_file import listdir
from portage_data import portage_gid

class config:
	def clone(self, clone):
		self.incrementals = copy.deepcopy(clone.incrementals)
		self.profile_path = copy.deepcopy(clone.profile_path)

		self.module_priority = copy.deepcopy(clone.module_priority)
		self.modules         = copy.deepcopy(clone.modules)
			
		self.depcachedir = copy.deepcopy(clone.depcachedir)

		self.packages = copy.deepcopy(clone.packages)
		self.virtuals = copy.deepcopy(clone.virtuals)

		self.use_defs = copy.deepcopy(clone.use_defs)
		self.usemask  = copy.deepcopy(clone.usemask)

		self.configlist = copy.deepcopy(clone.configlist)
		self.configlist[-1] = os.environ.copy()
		self.configdict = { "globals":   self.configlist[0],
		                    "defaults":  self.configlist[1],
		                    "conf":      self.configlist[2],
		                    "pkg":       self.configlist[3],
		                    "auto":      self.configlist[4],
		                    "backupenv": self.configlist[5],
		                    "env":       self.configlist[6] }
		self.backupenv  = copy.deepcopy(clone.backupenv)
		self.pusedict   = copy.deepcopy(clone.pusedict)
		self.categories = copy.deepcopy(clone.categories)
		self.pkeywordsdict = copy.deepcopy(clone.pkeywordsdict)
		self.pmaskdict = copy.deepcopy(clone.pmaskdict)
		self.punmaskdict = copy.deepcopy(clone.punmaskdict)
		self.prevmaskdict = copy.deepcopy(clone.prevmaskdict)
		self.pprovideddict = copy.deepcopy(clone.pprovideddict)
		self.lookuplist = copy.deepcopy(clone.lookuplist)
		self.uvlist     = copy.deepcopy(clone.uvlist)
		self.dirVirtuals = copy.deepcopy(clone.dirVirtuals)
		self.treeVirtuals = copy.deepcopy(clone.treeVirtuals)
		self.userVirtuals = copy.deepcopy(clone.userVirtuals)

	def __init__(self, clone=None, mycpv=None, config_profile_path=portage_const.PROFILE_PATH, config_incrementals=None):

		self.already_in_regenerate = 0

		self.locked   = 0
		self.mycpv    = None
		self.puse     = []
		self.modifiedkeys = []
	
		self.virtuals = {}
		self.v_count  = 0

		if clone:
			self.clone( clone )
		else:
			self.depcachedir = portage_const.DEPCACHE_PATH
			
			if not os.path.exists(config_profile_path):
				writemsg("config_profile_path not specified to class config\n")
				sys.exit(1)
			self.profile_path = config_profile_path

			if not config_incrementals:
				import traceback
				traceback.print_stack()
				writemsg("incrementals not specified to class config\n")
				writemsg("sayonara, sucker.\n")
				sys.exit(1)
			self.incrementals = copy.deepcopy(config_incrementals)
			
			self.module_priority    = ["user","default"]
			self.modules            = {}
			self.modules["user"]    = getconfig(portage_const.MODULES_FILE_PATH)
			if self.modules["user"] == None:
				self.modules["user"] = {}
			self.modules["default"] = {
				"portdbapi.metadbmodule": "cache.metadata.database",
				"portdbapi.auxdbmodule":  "cache.flat_list.database",
			}
			
			self.usemask=[]
			self.configlist=[]
			self.backupenv={}
			# back up our incremental variables:
			self.configdict={}
			# configlist will contain: [ globals, defaults, conf, pkg, auto, backupenv (incrementals), origenv ]

			# The symlink might not exist or might not be a symlink.
			try:
				self.profiles=[abssymlink(self.profile_path)]
			except (OSError, IOError):
				self.profiles=[self.profile_path]

			mypath = self.profiles[0]
			while os.path.exists(mypath+"/parent"):
				mypath = os.path.normpath(mypath+"///"+grabfile(mypath+"/parent")[0])
				if os.path.exists(mypath):
					self.profiles.insert(0,mypath)

			if os.environ.get("PORTAGE_CALLER",'') == "repoman":
				pass
			else:
				# XXX: This should depend on ROOT?
				if os.path.exists("/"+portage_const.CUSTOM_PROFILE_PATH):
					self.profiles.append("/"+portage_const.CUSTOM_PROFILE_PATH)

			self.packages_list = grab_multiple("packages", self.profiles, grabfile_package)
			self.packages      = stack_lists(self.packages_list, incremental=1)
			del self.packages_list
			#self.packages = grab_stacked("packages", self.profiles, grabfile, incremental_lines=1)

			# revmaskdict
			self.prevmaskdict={}
			for x in self.packages:
				mycatpkg=portage_dep.dep_getkey(x)
				if not self.prevmaskdict.has_key(mycatpkg):
					self.prevmaskdict[mycatpkg]=[x]
				else:
					self.prevmaskdict[mycatpkg].append(x)

			# get profile-masked use flags -- INCREMENTAL Child over parent
			usemask_lists = grab_multiple("use.mask", self.profiles, grabfile)
			self.usemask  = stack_lists(usemask_lists, incremental=True)
			del usemask_lists
			use_defs_lists = grab_multiple("use.defaults", self.profiles, grabdict)
			self.use_defs  = stack_dictlist(use_defs_lists, incremental=True)
			del use_defs_lists

			try:
				mygcfg_dlists = grab_multiple("make.globals", self.profiles+["/etc"], getconfig)
				self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=portage_const.INCREMENTALS, ignore_none=1)

				if self.mygcfg == None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
				writemsg("!!! Errors in this file should be reported on bugs.gentoo.org.\n")
				sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["globals"]=self.configlist[-1]

			self.mygcfg = {}
			if self.profiles:
				try:
					mygcfg_dlists = grab_multiple("make.defaults", self.profiles, getconfig)
					self.mygcfg   = stack_dicts(mygcfg_dlists, incrementals=self.incrementals[:], ignore_none=1)
					#self.mygcfg = grab_stacked("make.defaults", self.profiles, getconfig)
					if self.mygcfg == None:
						self.mygcfg = {}
				except SystemExit, e:
					raise
				except Exception, e:
					writemsg("!!! %s\n" % (e))
					writemsg("!!! 'rm -Rf /usr/portage/profiles; emerge sync' may fix this. If it does\n")
					writemsg("!!! not then please report this to bugs.gentoo.org and, if possible, a dev\n")
					writemsg("!!! on #gentoo (irc.freenode.org)\n")
					sys.exit(1)
			self.configlist.append(self.mygcfg)
			self.configdict["defaults"]=self.configlist[-1]

			try:
				# XXX: Should depend on root?
				self.mygcfg=getconfig("/"+portage_const.MAKE_CONF_FILE)
				if self.mygcfg == None:
					self.mygcfg = {}
			except SystemExit, e:
				raise
			except Exception, e:
				writemsg("!!! %s\n" % (e))
				writemsg("!!! Incorrect multiline literals can cause this. Do not use them.\n")
				sys.exit(1)
			

			self.configlist.append(self.mygcfg)
			self.configdict["conf"]=self.configlist[-1]

			self.configlist.append({})
			self.configdict["pkg"]=self.configlist[-1]

			#auto-use:
			self.configlist.append({})
			self.configdict["auto"]=self.configlist[-1]

			#backup-env (for recording our calculated incremental variables:)
			self.backupenv = os.environ.copy()
			self.configlist.append(self.backupenv) # XXX Why though?
			self.configdict["backupenv"]=self.configlist[-1]

			self.configlist.append(os.environ.copy())
			self.configdict["env"]=self.configlist[-1]

			# make lookuplist for loading package.*
			self.lookuplist=self.configlist[:]
			self.lookuplist.reverse()

			archlist = grabfile(self["PORTDIR"]+"/profiles/arch.list")
			self.configdict["conf"]["PORTAGE_ARCHLIST"] = ' '.join(archlist)

			if os.environ.get("PORTAGE_CALLER",'') == "repoman":
				# repoman shouldn't use local settings.
				locations = [self["PORTDIR"] + "/profiles"]
				self.pusedict = {}
				self.pkeywordsdict = {}
				self.punmaskdict = {}
			else:
				locations = [self["PORTDIR"] + "/profiles", portage_const.USER_CONFIG_PATH]

				# Never set anything in this. It's for non-originals.
				self.pusedict=grabdict_package(portage_const.USER_CONFIG_PATH+"/package.use")

				#package.keywords
				pkgdict=grabdict_package(portage_const.USER_CONFIG_PATH+"/package.keywords")
				self.pkeywordsdict = {}

				for key in pkgdict.keys():
					# default to ~arch if no specific keyword is given
					if not pkgdict[key]:
						mykeywordlist = []
						if self.configdict["defaults"] and self.configdict["defaults"].has_key("ACCEPT_KEYWORDS"):
							groups = self.configdict["defaults"]["ACCEPT_KEYWORDS"].split()
						else:
							groups = []
						for keyword in groups:
							if not keyword[0] in "~-":
								mykeywordlist.append("~"+keyword)
						pkgdict[key] = mykeywordlist
					cp = portage_dep.dep_getkey(key)
					if not self.pkeywordsdict.has_key(cp):
						self.pkeywordsdict[cp] = {}
					self.pkeywordsdict[cp][key] = pkgdict[key]

				#package.unmask
				pkgunmasklines = grabfile_package(portage_const.USER_CONFIG_PATH+"/package.unmask")
				self.punmaskdict = {}
				for x in pkgunmasklines:
					mycatpkg=portage_dep.dep_getkey(x)
					L = self.punmaskdict.setdefault(mycatpkg,[])
					L.append(x)

			#getting categories from an external file now
			categories = grab_multiple("categories", locations, grabfile)
			self.categories = stack_lists(categories, incremental=1)
			del categories

			# get virtuals -- needs categories
			self.loadVirtuals('/')
					
			#package.mask
			# Don't enable per profile package.mask unless the profile
			# specifically depends on the >=portage-2.0.51 using
			# <portage-2.0.51 syntax.
			# don't hardcode portage versions into portage.  It's not nice.
			if self.profiles and (">=sys-apps/portage-2.0.51" in self.packages \
                                      or "*>=sys-apps/portage-2.0.51" in self.packages):
				pkgmasklines = grab_multiple("package.mask", self.profiles + locations, grabfile_package)
			else:
				pkgmasklines = grab_multiple("package.mask", locations, grabfile_package)
			pkgmasklines = stack_lists(pkgmasklines, incremental=1)

			self.pmaskdict = {}
			for x in pkgmasklines:
				mycatpkg = portage_dep.dep_getkey(x)
				L = self.pmaskdict.setdefault(mycatpkg,[])
				L.append(x)

			pkgprovidedlines = grab_multiple("package.provided", self.profiles, grabfile)
			pkgprovidedlines = stack_lists(pkgprovidedlines, incremental=1)

			self.pprovideddict = {}
			for x in pkgprovidedlines:
				cpv=portage_versions.catpkgsplit(x)
				if not x:
					continue
				mycatpkg=portage_dep.dep_getkey(x)
				L = self.pprovideddict.setdefault(mycatpkg,[])
				L.append(x)


		self.lookuplist=self.configlist[:]
		self.lookuplist.reverse()
	
		useorder=self["USE_ORDER"]
		if not useorder:
			# reasonable defaults; this is important as without USE_ORDER,
			# USE will always be "" (nothing set)!
			useorder="env:pkg:conf:auto:defaults"
		useordersplit=useorder.split(":")

		self.uvlist=[]
		for x in useordersplit:
			if x in self.configdict:
				if "PKGUSE" in self.configdict[x]:
					# Delete PkgUse, Not legal to set.
					del self.configdict[x]["PKGUSE"]
				#prepend db to list to get correct order
				self.uvlist.insert(0,self.configdict[x])

		self.configdict["env"]["PORTAGE_GID"]=str(portage_gid)
		self.backupenv["PORTAGE_GID"]=str(portage_gid)

		if self.has_key("PORT_LOGDIR") and not self["PORT_LOGDIR"]:
			# port_logdir is defined, but empty.  this causes a traceback in doebuild.
			writemsg(yellow("!!!")+" PORT_LOGDIR was defined, but set to nothing.\n")
			writemsg(yellow("!!!")+" Disabling it.  Please set it to a non null value.\n")
			del self["PORT_LOGDIR"]

		if self["PORTAGE_CACHEDIR"]:
			# XXX: Deprecated -- April 15 -- NJ
			writemsg(yellow(">>> PORTAGE_CACHEDIR has been deprecated!")+"\n")
			writemsg(">>> Please use PORTAGE_DEPCACHEDIR instead.\n")
			self.depcachedir = self["PORTAGE_CACHEDIR"]
			del self["PORTAGE_CACHEDIR"]

		if self["PORTAGE_DEPCACHEDIR"]:
			#the auxcache is the only /var/cache/edb/ entry that stays at / even when "root" changes.
			# XXX: Could move with a CHROOT functionality addition.
			self.depcachedir = self["PORTAGE_DEPCACHEDIR"]
			del self["PORTAGE_DEPCACHEDIR"]

		overlays = self["PORTDIR_OVERLAY"].split()
		if overlays:
			new_ov=[]
			for ov in overlays:
				ov=os.path.normpath(ov)
				if os.path.isdir(ov):
					new_ov.append(ov)
				else:
					writemsg(red("!!! Invalid PORTDIR_OVERLAY (not a dir): "+ov+"\n"))
			self["PORTDIR_OVERLAY"] = " ".join(new_ov)
			self.backup_changes("PORTDIR_OVERLAY")

		self.regenerate()
		
		
		self.features = portage_util.unique_array(self["FEATURES"].split())
		self.features.sort()

		#XXX: Should this be temporary? Is it possible at all to have a default?
		if "gpg" in self.features:
			if not os.path.exists(self["PORTAGE_GPG_DIR"]) or not os.path.isdir(self["PORTAGE_GPG_DIR"]):
				writemsg("PORTAGE_GPG_DIR is invalid. Removing gpg from FEATURES.\n")
				self.features.remove("gpg")
				self["FEATURES"] = " ".join(self.features)
				self.backup_changes("FEATURES")
		
		if mycpv:
			self.setcpv(mycpv)

	def autouse(self, myvartree, use_cache=1):
		"returns set of USE variables auto-enabled due to packages being installed"
		# XXX: harring wonders why profiledir is checked here...
		from portage import profiledir
		if profiledir==None:
			return ""
		myusevars=""
		for myuse in self.use_defs:
			dep_met = True
			for mydep in self.use_defs[myuse]:
				if not myvartree.dep_match(mydep,use_cache=True):
					dep_met = False
					break
			if dep_met:
				myusevars += " "+myuse
		return myusevars



	def loadVirtuals(self,root):
		self.virtuals = self.getvirtuals(root)

	def load_best_module(self,property_string):
		best_mod = best_from_dict(property_string,self.modules,self.module_priority)
		return load_mod(best_mod)
			
	def lock(self):
		self.locked = 1

	def unlock(self):
		self.locked = 0
	
	def modifying(self):
		if self.locked:
			raise Exception, "Configuration is locked."
	
	def backup_changes(self,key=None):
		if key and self.configdict["env"].has_key(key):
			self.backupenv[key] = copy.deepcopy(self.configdict["env"][key])
		else:
			raise KeyError, "No such key defined in environment: %s" % key
	
	def reset(self,keeping_pkg=0,use_cache=1):
		"reset environment to original settings"
		envdict = self.configdict["env"]
		# reinitialize env values to those of backupenv
		envdict.clear()
		envdict.update(self.backupenv)
		self.modifiedkeys = []
		if not keeping_pkg:
			self.puse = ""
			self.configdict["pkg"].clear()
		self.regenerate(use_cache=use_cache)

	def load_infodir(self,infodir):
		if self.configdict.has_key("pkg"):
			self.configdict["pkg"].clear()
		else:
			writemsg("No pkg setup for settings instance?\n")
			sys.exit(17)
		
		if os.path.exists(infodir):
			if os.path.exists(infodir+"/environment"):
				self.configdict["pkg"]["PORT_ENV_FILE"] = infodir+"/environment"
			elif os.path.exists(infodir+"/environment.bz2"):
				self.configdict["pkg"]["PORT_ENV_FILE"] = infodir+"/environment.bz2"
#			else:
#				print "wth, no env found in the infodir, '%s'" % infodir
#				import traceback
#				traceback.print_stack()
#				sys.exit(15)
			myre = re.compile('^[A-Z]+$')
			for filename in listdir(infodir,filesonly=1):
				if myre.match(filename):
					try:
						mydata = open(infodir+"/"+filename).read().strip()
						if len(mydata)<2048:
							if filename == "USE":
								self.configdict["pkg"][filename] = "-* "+mydata
							else:
								self.configdict["pkg"][filename] = mydata
					except SystemExit, e:
						raise
					except:
						writemsg("!!! Unable to read file: %s\n" % infodir+"/"+filename)
						pass
			return 1
		return 0

	def setcpv(self,mycpv,use_cache=1):
		self.modifying()
		self.mycpv = mycpv
		self.pusekey = portage_dep.best_match_to_list(self.mycpv, self.pusedict.keys())
		if self.pusekey:
			newpuse = " ".join(self.pusedict[self.pusekey])
		else:
			newpuse = ""
		if newpuse == self.puse:
			return
		self.puse = newpuse
		self.configdict["pkg"]["PKGUSE"] = self.puse[:] # For saving to PUSE file
		self.configdict["pkg"]["USE"]    = self.puse[:] # this gets appended to USE
		self.reset(keeping_pkg=1,use_cache=use_cache)

	def setinst(self,mycpv,mydbapi):
		"""
		Grab the virtuals this package provides and add them into the tree virtuals.
		"""
		provides = mydbapi.aux_get(mycpv, ["PROVIDE"])[0]

		#XXX HACK
		from portage import portdbapi

		if isinstance(mydbapi, portdbapi):
			myuse = self["USE"]
		else:
			myuse = mydbapi.aux_get(mycpv, ["USE"])[0]
		virts = flatten(portage_dep.use_reduce(portage_dep.paren_reduce(provides), uselist=myuse.split()))

		cp = portage_dep.dep_getkey(mycpv)
		for virt in virts:
			virt = portage_dep.dep_getkey(virt)
			if not self.treeVirtuals.has_key(virt):
				self.treeVirtuals[virt] = []
			self.treeVirtuals[virt] = portage_util.unique_array(self.treeVirtuals[virt]+[cp])
		# Reconstruct the combined virtuals.
		val = stack_dictlist( [self.userVirtuals, self.treeVirtuals]+self.dirVirtuals, incremental=1)
		for v in val.values():
			v.reverse()
		self.virtuals = val
	
	def regenerate(self,useonly=0,use_cache=1):		
		if self.already_in_regenerate:
			# XXX: THIS REALLY NEEDS TO GET FIXED. autouse() loops.
			writemsg("!!! Looping in regenerate.\n",1)
			return
		else:
			self.already_in_regenerate = 1

		if useonly:
			myincrementals=["USE"]
		else:
			myincrementals=self.incrementals[:]

		# XXX HACK, harring
		# this is a design flaw of the code.
		from portage import db, root

		rootdb = db.get(root)
		for mykey in myincrementals:
			if mykey=="USE":
				mydbs=self.uvlist
				# XXX Global usage of db... Needs to go away somehow.
				if rootdb and "vartree" in rootdb:
					_use = self.autouse( rootdb["vartree"], use_cache=use_cache)
				else:
					_use = ""
				self.configdict["auto"]["USE"]= _use
			else:
				mydbs=self.configlist[:-1]

			myflags=[]
			for curdb in mydbs:
				if mykey not in curdb:
					continue
				#variables are already expanded
				mysplit=curdb[mykey].split()
				
				for x in mysplit:
					if x=="-*":
						# "-*" is a special "minus" var that means "unset all settings".
						# so USE="-* gnome" will have *just* gnome enabled.
						myflags=[]
						continue

					if x[0]=="+":
						# Not legal. People assume too much. Complain.
						writemsg(red("USE flags should not start with a '+': %s\n" % x))
						x=x[1:]

					if x[0]=="-":
						if x[1:] in myflags:
							# Unset/Remove it.
							myflags.remove(x[1:])
						continue

					# We got here, so add it now.
					if x not in myflags:
						myflags.append(x)

			myflags.sort()
			#store setting in last element of configlist, the original environment:
			self.configlist[-1][mykey]=" ".join(myflags)
			del myflags

		#cache split-up USE var in a global
		usesplit=[]

		for x in self.configlist[-1]["USE"].split():
			if x not in self.usemask:
				usesplit.append(x)

		if self.has_key("USE_EXPAND"):
			for var in self["USE_EXPAND"].split():
				if self.has_key(var):
					for x in self[var].split():
						mystr = var.lower()+"_"+x
						if mystr not in usesplit:
							usesplit.append(mystr)

		# Pre-Pend ARCH variable to USE settings so '-*' in env doesn't kill arch.
		# XXX: harring wonders why profiledir is checked here...
		from portage import profiledir
		if profiledir:
			if self.configdict["defaults"].has_key("ARCH"):
				if self.configdict["defaults"]["ARCH"]:
					if self.configdict["defaults"]["ARCH"] not in usesplit:
						usesplit.insert(0,self.configdict["defaults"]["ARCH"])

		self.configlist[-1]["USE"]=" ".join(usesplit)

		self.already_in_regenerate = 0

	def getvirtuals(self, myroot):
		myvirts     = {}

		# This breaks catalyst/portage when setting to a fresh/empty root.
		# Virtuals cannot be calculated because there is nothing to work
		# from. So the only ROOT prefixed dir should be local configs.
		#myvirtdirs  = prefix_array(self.profiles,myroot+"/")
		myvirtdirs = copy.deepcopy(self.profiles)
		
		self.treeVirtuals = {}

		# Repoman should ignore these.
		user_profile_dir = None
		if os.environ.get("PORTAGE_CALLER","") != "repoman":
			user_profile_dir = myroot+portage_const.USER_CONFIG_PATH
		
		# XXX: Removing this as virtuals and profile/virtuals behave
		# differently. portage/profile/virtuals overrides the default
		# virtuals but are overridden by installed virtuals whereas
		# portage/virtuals overrides everything.
		
		#if os.path.exists("/etc/portage/virtuals"):
		#	writemsg("\n\n*** /etc/portage/virtuals should be moved to /etc/portage/profile/virtuals\n")
		#	writemsg("*** Please correct this by merging or moving the file. (Deprecation notice)\n\n")
		#	time.sleep(1)
		
		
		self.dirVirtuals = grab_multiple("virtuals", myvirtdirs, grabdict)
		self.dirVirtuals.reverse()
		self.userVirtuals = {}
		if user_profile_dir and os.path.exists(user_profile_dir+"/virtuals"):
			self.userVirtuals = grabdict(user_profile_dir+"/virtuals")

		# User settings and profile settings take precedence over tree.
		profile_virtuals = stack_dictlist([self.userVirtuals]+self.dirVirtuals,incremental=1)
		
		# repoman doesn't need local virtuals
		if os.environ.get("PORTAGE_CALLER","") != "repoman":
			from portage import vartree
			temp_vartree = vartree(myroot,profile_virtuals,categories=self.categories)
			myTreeVirtuals = {}
			for key, val in temp_vartree.get_all_provides().items():
				myTreeVirtuals[key] = portage_util.unique_array( [ portage_versions.pkgsplit(x)[0] for x in val ] )
			self.treeVirtuals.update(myTreeVirtuals)
			del myTreeVirtuals
#			myTreeVirtuals = map_dictlist_vals(getCPFromCPV,temp_vartree.get_all_provides())
#			for x,v in myTreeVirtuals.items():
#				self.treeVirtuals[x] = portage_util.unique_array(v)
			
		# User settings and profile settings take precedence over tree
		val = stack_dictlist([self.userVirtuals,self.treeVirtuals]+self.dirVirtuals,incremental=1)
		
		for x in val.values():
			x.reverse()
		return val
	
	def __delitem__(self,mykey):
		for x in self.lookuplist:
			if x != None:
				if mykey in x:
					del x[mykey]
	
	def __getitem__(self,mykey):
		match = ''
		for x in self.lookuplist:
			if x == None:
				writemsg("!!! lookuplist is null.\n")
			elif x.has_key(mykey):
				match = x[mykey]
				break

		if 0 and match and mykey in ["PORTAGE_BINHOST"]:
			# These require HTTP Encoding
			try:
				import urllib
				if urllib.unquote(match) != match:
					writemsg("Note: %s already contains escape codes." % (mykey))
				else:
					match = urllib.quote(match)
			except SystemExit, e:
				raise
			except:
				writemsg("Failed to fix %s using urllib, attempting to continue.\n"  % (mykey))
				pass
			
		elif mykey == "CONFIG_PROTECT_MASK":
			match += " /etc/env.d"

		return match

	def has_key(self,mykey):
		for x in self.lookuplist:
			if x.has_key(mykey):
				return 1 
		return 0
	
	def keys(self):
		mykeys=[]
		for x in self.lookuplist:
			for y in x.keys():
				if y not in mykeys:
					mykeys.append(y)
		return mykeys

	def __setitem__(self,mykey,myvalue):
		"set a value; will be thrown away at reset() time"
		if not isinstance(myvalue, str):
			raise ValueError("Invalid type being used as a value: '%s': '%s'" % (str(mykey),str(myvalue)))
		self.modifying()
		self.modifiedkeys += [mykey]
		self.configdict["env"][mykey]=myvalue
	
	def environ(self):
		"return our locally-maintained environment"
		mydict={}
		for x in self.keys(): 
			mydict[x]=self[x]
		if not mydict.has_key("HOME") and mydict.has_key("BUILD_PREFIX"):
			writemsg("*** HOME not set. Setting to "+mydict["BUILD_PREFIX"]+"\n")
			mydict["HOME"]=mydict["BUILD_PREFIX"][:]

		return mydict

	def bash_environ(self):
		"return our locally-maintained environment in a suitable bash assignment form"
		mydict=self.environ()
		final={}
		for k in mydict.keys():
			# quotes and escaped chars suck.
			s=mydict[k].replace("\\","\\\\\\\\")
			s=s.replace("'","\\\\'")
			s=s.replace("\n","\\\n")
			final[k]="$'%s'" % s
		return final


def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = None
	for mydict in dicts:
		if mydict == None:
			if ignore_none:
				continue
			else:
				return None
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if mydict[y]:
				if final_dict.has_key(y) and (incremental or (y in incrementals)):
					final_dict[y] += " "+mydict[y][:]
				else:
					final_dict[y]  = mydict[y][:]
			mydict[y] = ' '.join(mydict[y].split()) # Remove extra spaces.
	return final_dict

def stack_lists(lists, incremental=1):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced."""
	new_list = []
	for x in lists:
		for y in x:
			if y:
				if incremental and y[0]=='-':
					while y[1:] in new_list:
						del new_list[new_list.index(y[1:])]
				else:
					if y not in new_list:
						new_list.append(y[:])
	return new_list

def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced."""
	final_dict = None
	kill_list = {}
	for mydict in original_dicts:
		if mydict == None:
			continue
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if not final_dict.has_key(y):
				final_dict[y] = []
			if not kill_list.has_key(y):
				kill_list[y] = []
			
			for thing in mydict[y]:
				if thing and (thing not in kill_list[y]):
					if (incremental or (y in incrementals)) and thing[0] == '-':
						if thing[1:] not in kill_list[y]:
							kill_list[y] += [thing[1:]]
#						while(thing[1:] in final_dict[y]):
#							del final_dict[y][final_dict[y].index(thing[1:])]
					else:
						if thing not in final_dict[y]:
							final_dict[y].insert(0,thing[:])
			if final_dict.has_key(y) and not final_dict[y]:
				del final_dict[y]
	return final_dict


def best_from_dict(key, top_dict, key_order, EmptyOnError=1, FullCopy=1, AllowEmpty=1):
	for x in key_order:
		dico = top_dict.get(x)
		if dico and key in dico:
			if FullCopy:
				return copy.deepcopy(dico[key])
			else:
				return dico[key]
	if EmptyOnError:
		return ""
	else:
		raise KeyError, "Key not found in list; '%s'" % key


def load_mod(name):
	components = name.split('.')
	modname = ".".join(components[:-1])
	mod = __import__(modname)
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod
