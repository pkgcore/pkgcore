# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: fetchcommand.py 1936 2005-08-26 05:37:15Z ferringb $

import os, shutil
from portage.operations import build, repo
from itertools import imap, izip
from portage.ebuild.processor import request_ebuild_processor, release_ebuild_processor, UnhandledCommand, \
	expected_ebuild_env, chuck_UnhandledCommand
from portage.os_data import portage_gid
from portage.fs.util import ensure_dirs, normpath
from portage.os_data import portage_gid
from portage.spawn import spawn_bash, spawn
from portage.util.currying import post_curry, pretty_docs
from portage.os_data import xargs
from const import eapi_capable
from portage.ebuild.ebuild_built import built
from portage.fs import scan
from portage.interfaces.data_source import local_source


class ebd(object):

	def __init__(self, pkg, env=None, features=None):
		if pkg.eapi not in eapi_capable:
			raise TypeError("pkg isn't of a supported eapi!, %i not in %s for %s" % (pkg.eapi, eapi_capable, pkg))

		if env is not None:
			# copy.
			self.env = dict(env)
			for x in ("USE", "ACCEPT_LICENSE"):
				if x in self.env:
					del self.env[x]
		else:
			self.env = {}

		if features is None:
			features = self.env.get("FEATURES", [])

		self.features = set(map(lambda x:x.lower(), features))

		if "FEATURES" in self.env:
			del self.env["FEATURES"]
			
		expected_ebuild_env(pkg, self.env)

		self.env["USE"] = ' '.join(imap(str, pkg.use))
		self.env["INHERITED"] = ' '.join(pkg.data.get("_eclasses_", {}).keys())

		self.restrict = pkg.data["RESTRICT"].split()
		
		for x in ("sandbox", "userpriv", "fakeroot"):
			setattr(self, x, self.feat_or_bool(x) and not (x in self.restrict))
		
		if "PORT_LOGDIR" in self.env:
			self.logging = os.path.join(self.env["PORT_LOGDIR"], pkg.category, pkg.cpvstr+".log")
			del self.env["PORT_LOGDIR"]
		else:
			self.logging = False
		
		self.env["XARGS"] = xargs

		self.bashrc = self.env.get("bashrc", [])
		if self.bashrc:
			del self.env["bashrc"]

		self.pkg = pkg
		self.eapi = pkg.eapi
		for k,v in self.env.items():
			if not isinstance(v, basestring):
				del self.env[k]

	def __init_workdir__(self):
		# don't fool with this, without fooling with setup.
		tmp = self.env["PORTAGE_TMPDIR"]
		del self.env["PORTAGE_TMPDIR"]
		prefix = normpath(os.path.join(tmp, "portage"))
		self.env["HOME"] = os.path.join(prefix, "homedir")

		self.builddir = os.path.join(prefix, self.env["CATEGORY"], self.env["PF"])
		for x,y in (("T","temp"),("WORKDIR","work"), ("D","image")):
			self.env[x] = os.path.join(self.builddir, y) +"/"
		self.env["IMAGE"] = self.env["D"]


	def setup_logging(self):
		if self.logging and not ensure_dirs(os.path.dirname(self.env["PORT_LOGFILE"]), mode=02770, gid=portage_gid):
			raise build.FailedDirectory(self.env["PORT_LOGFILE"], "failed ensuring PORT_LOGDIR as 02770 and %i" % portage_gid)

	def setup_workdir(self):
		# ensure dirs.
		for k, text in (("HOME", "home"), ("T", "temp"), ("WORKDIR", "work"), ("D", "image")):
			if not ensure_dirs(self.env[k], mode=0770, gid=portage_gid):
				raise build.FailedDirectory(self.env[k], "required: %s directory" % text)

	def setup(self):
		self.setup_workdir()
		self.setup_distfiles()
		self.setup_logging()
		ebd = request_ebuild_processor(userpriv=False, sandbox=self.sandbox)
		try:
			ebd.prep_phase("setup", self.env, sandbox=self.sandbox, logging=self.logging)
			ebd.write("start_processing")
			if not ebd.generic_handler(additional_commands={"request_inherit":post_curry(ebd.__class__._inherit, self.eclass_cache),
				"request_profiles":self._request_bashrcs}):
				raise build.GenericBuildError("setup: Failed building (False/0 return from handler)")
		except Exception, e:
			# regardless of what occured, we kill the processor.
			ebd.shutdown_processor()
			release_ebuild_processor(ebd)
			# either we know what it is, or it's a shutdown.  re-raise
			if isinstance(e, (SystemExit, build.GenericBuildError)):
				raise
			# wrap.
			raise build.GenericBuildError("setup: Caught exception while building: " + str(e))

		release_ebuild_processor(ebd)
		return True

	def _request_bashrcs(self, ebd, a):
		if a != None:
			chuck_UnhandledCommand("bashrc request with arg"+str(a))
		for source in self.bashrc:
			if source.get_path != None:
				ebd.write("path\n%s" % source.get_path())
			elif source.get_data != None:
				ebd.write("transfer\n%s" % source.get_data())
			else:
				chuck_UnhandledCommand("bashrc request: unable to process bashrc '%s' due to source '%s' due to lacking"+
					"usable get_*" % (val, source))
			if not ebd.expect("next"):
				chuck_UnhandledCommand("bashrc transfer, didn't receive 'next' response.  failure?")
		ebd.write("end_request")

	def _generic_phase(self, phase, userpriv, sandbox, fakeroot):
		ebd = request_ebuild_processor(userpriv=(self.userpriv and userpriv), 
			sandbox=(self.sandbox and sandbox), fakeroot=(self.fakeroot and fakeroot))
		try:
			ebd.prep_phase(phase, self.env, sandbox=self.sandbox, logging=self.logging)
			ebd.write("start_processing")
			if not ebd.generic_handler():
				raise build.GenericBuildError(phase + ": Failed building (False/0 return from handler)")

		except Exception, e:
			ebd.shutdown_processor()
			release_ebuild_processor(ebd)
			if isinstance(e, (SystemExit, build.GenericBuildError)):
				raise
			raise build.GenericBuildError(phase + ": Caught exception while building: %s" % e)

		release_ebuild_processor(ebd)
		return True

	def clean(self):
		if not os.path.exists(self.builddir):
			return True
		try:
			shutil.rmtree(self.builddir)
		except OSError, oe:
			raise build.GenericBuildError("clean: Caught exception while cleansing: %s" % oe)
		return True


	def feat_or_bool(self, name, extra_env=None):
		if name in self.env:
			v = bool(self.env[name])
			del d[name]
			name = name.lower()
			if v:
				self.features.add(name)
			else:
				if name in self.features:
					self.features.remove(name)
		elif extra_env is not None and name in extra_env:
			v = bool(extra_env[name])
			if v:
				self.features.add(name.lower())
			else:
				self.features.remove(name.lower())
		else:
			v = name.lower() in self.features
		return v


class install_op(ebd):
	preinst = pretty_docs(post_curry(ebd._generic_phase, "preinst", False, False, False), "run the preinst phase")
	postinst = pretty_docs(post_curry(ebd._generic_phase, "postinst", False, False, False), "run the postinst phase")


class uninstall_op(ebd):
	prerm = pretty_docs(post_curry(ebd._generic_phase, "prerm", False, False, False), "run the prerm phase")
	postrm = pretty_docs(post_curry(ebd._generic_phase, "postrm", False, False, False), "run the postrm phase")


class replace_op(install_op, uninstall_op):
	pass


class buildable(ebd, build.base):
	_built_class = built
	
	# XXX this is unclean- should be handing in strictly what is build env, rather then
	# dumping domain settings as env. 
	def __init__(self, pkg, domain_settings, eclass_cache, fetcher):
		build.base.__init__(self)
		ebd.__init__(self, pkg, env=domain_settings, features=domain_settings["FEATURES"])
		self.__init_workdir__()
		
		self.env["FILESDIR"] = os.path.join(os.path.dirname(pkg.path), "files")
		self.eclass_cache = eclass_cache
		self.fetcher = fetcher

		self.run_test = self.feat_or_bool("test", domain_settings) and not "test" in self.restrict

		# XXX minor hack
		path = self.env["PATH"].split(":")

		for s in ("DISTCC", "CCACHE"):
			b = (self.feat_or_bool(s, domain_settings) and not s in self.restrict)
			setattr(self, s.lower(), b)
			if b:
				path.insert(0, self.env[s+"_PATH"])
				# looks weird I realize, but os.path.join("/foor/bar", "/barr/foo") == "/barr/foo"
				# and os.path.join("/foo/bar",".asdf") == "/foo/bar/.asdf"
				self.env[s+"_DIR"] = os.path.join(tmp, self.env[s+"_DIR"])
				for x in ("CC", "CXX"):
					if x in self.env:
						self.env[x] = "%s %s" % (s.lower(), self.env[x])
					else:
						self.env[x] = s.lower()
			else:
				for y in ("_PATH", "_DIR"):
					if s+y in self.env:
						del self.env[s+y]
		
		self.env["PATH"] = ":".join(path)
		path = filter(None, path)
		self.fetchables = pkg.fetchables[:]
		self.env["A"] = ' '.join(map(lambda x: x.filename, self.fetchables))

	def setup_distfiles(self):
		if len(self.files):
			# cvs/svn ebuilds need to die.
			#self.env["PORTAGE_ACTUAL_DISTDIR"] = self.env["DISTDIR"]
			self.env["DISTDIR"] = normpath(os.path.join(self.builddir, "distdir"))+"/"

			try:
				if os.path.exists(self.env["DISTDIR"]):
					if os.path.isdir(self.env["DISTDIR"]) and not os.path.islink(self.env["DISTDIR"]):
						shutil.rmtree(self.env["DISTDIR"])
					else:
						os.unlink(self.env["DISTDIR"])

			except OSError, oe:
				raise build.FailedDirectory(self.env["DISTDIR"], "failed removing existing file/dir/link at: exception %s" % oe)
				
			if not ensure_dirs(self.env["DISTDIR"], mode=0770, gid=portage_gid):
				raise build.FailedDirectory(self.env["DISTDIR"], "failed creating distdir symlink directory")

			try:
				for src, dest in [(k, os.path.join(self.env["DISTDIR"], v.filename)) for (k,v) in self.files.items()]:
					os.symlink(src,dest)

			except OSError, oe:
				raise build.GenericBuildError("Failed symlinking in distfiles for src %s -> %s: %s" % (src, dest, str(oe)))


	def setup(self):
		if self.distcc:
			for p in ("", "/lock", "/state"):
				if not ensure_dirs(os.path.join(self.env["DISTCC_DIR"], p), mode=02775, gid=portage_gid):
					raise build.FailedDirectory(os.path.join(self.env["DISTCC_DIR"], p), "failed creating needed distcc directory")
		if self.ccache:
			# yuck.
			st = None
			try:	st = os.stat(self.env["CCACHE_DIR"])
			except OSError:
				st = None
				if not ensure_dirs(self.env["CCACHE_DIR"], mode=02775, gid=portage_gid):
					raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed creation of ccache dir")
			if st == None:
				try:
					if st.gid != portage_gid or (st.st_mode & 02070) != 02070:
						try:	cwd = os.getcwd()
						except OSError:	cwd = "/"
						try:
							# crap.
							os.chmod(self.env["CCACHE_DIR"], 02775)
							os.chown(self.env["CCACHE_DIR"], -1, portage_gid)
							os.chdir(cwd)
							if 0 != spawn(["chgrp", "-R", str(portage_gid)]):
								raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed changing ownership for CCACHE_DIR")
							if 0 != spawn_bash("find . -type d | %s chmod 02775" % xargs):
								raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed correcting perms for CCACHE_DIR")
						finally:
							os.chdir(cwd)
				except OSError:
					raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed ensuring perms/group owner for CCACHE_DIR")

		return ebd.setup(self)


	def configure(self):
		if self.eapi > 0:
			return self._generic_phase("configure", True, True, False)
		return True

	unpack = pretty_docs(post_curry(ebd._generic_phase, "unpack", True, True, False), "run the unpack phase")
	compile = pretty_docs(post_curry(ebd._generic_phase, "compile", True, True, False), "run the compile phase")	

	def install(self):
		"""install phase"""
		if self.fakeroot:
			return self._generic_phase("install", True, False, True)
		else:
			return self._generic_phase("install", True, True, False)

	def test(self):
		"""run the test phase (if enabled)"""
		if not self.run_test:
			return True
		return self._generic_phase("test", True, True, False)

	def finalize(self):
		return self._built_class(self.pkg, scan(self.env["IMAGE"], offset=self.env["IMAGE"]), 
			environment=local_source(os.path.join(self.env["T"], "environment")))

