# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: fetchcommand.py 1936 2005-08-26 05:37:15Z ferringb $

import os, shutil
# surprisingly this is clean, cause buildable defines __all__
from portage.operations.build import *
from itertools import imap, izip
from portage.ebuild.processor import request_ebuild_processor, release_ebuild_processor, UnhandledCommand, \
	expected_ebuild_env, chuck_UnhandledCommand
from portage.os_data import portage_gid
from portage.util.fs import ensure_dirs, normpath
from portage.os_data import portage_gid
from portage.spawn import spawn_bash, spawn
from portage.util.currying import post_curry, pretty_docs
from portage.os_data import xargs
from const import eapi_capable
from portage.ebuild.ebuild_built import built
from portage.fs import scan
from portage.protocols.data_source import local_source

def feat_or_bool(d, name):
	if name in d:
		v = d[name]
		del d[name]
		return bool(v)
	return name in d["FEATURES"]

class buildable(base):
	_built_class = built
	
	# XXX this is unclean- should be handing in strictly what is build env, rather then
	# dumping domain settings as env. 
	def __init__(self, pkg, domain_settings, eclass_cache, fetcher):
		if pkg.eapi not in eapi_capable:
			raise TypeError("pkg isn't of a supported eapi!, %i not in %s for %s" % (pkg.eapi, eapi_capable, pkg))
		super(buildable, self).__init__()

		# copy.
		d = dict(domain_settings)
		for x in ("USE", "ACCEPT_LICENSE"):
			if x in d:
				del d[x]

		expected_ebuild_env(pkg, d)
		d["USE"] = ' '.join(imap(str, pkg.use))
		d["FILESDIR"] = os.path.join(os.path.dirname(pkg.path), "files")
		# don't fool with this, without fooling with setup.
		tmp = d["PORTAGE_TMPDIR"]
		del d["PORTAGE_TMPDIR"]
		prefix = normpath(os.path.join(tmp, "portage"))
		d["HOME"] = os.path.join(prefix, "homedir")

		self.builddir = os.path.join(prefix, d["CATEGORY"], d["PF"])
		for x,y in (("T","temp"),("WORKDIR","work"), ("D","image")):
			d[x] = os.path.join(self.builddir, y) +"/"
		d["IMAGE"] = d["D"]

		d["INHERITED"] = ' '.join(pkg.data.get("_eclasses_", {}).keys())
		self.restrict = set(pkg.data["RESTRICT"].split())
		for x in ("sandbox", "userpriv", "fakeroot", "ccache", "distcc"):
			setattr(self, x, feat_or_bool(d, x) and not x in self.restrict)
		self.run_test = feat_or_bool(d, "test") and not "test" in self.restrict
		
		if "PORT_LOGDIR" in d:
			self.logging = os.path.join(d["PORT_LOGDIR"], pkg.category, pkg.cpvstr+".log")
			del d["PORT_LOGDIR"]
		else:	self.logging = False

		# XXX minor hack
		path = d["PATH"].split(":")
		nuke = []

		for b, s in ((self.distcc, "DISTCC"), (self.ccache, "CCACHE")):
			if b:
				path.insert(0, d[s+"_PATH"])
				# looks weird I realize, but os.path.join("/foor/bar", "/barr/foo") == "/barr/foo"
				# and os.path.join("/foo/bar",".asdf") == "/foo/bar/.asdf"
				d[s+"_DIR"] = os.path.join(tmp, d[s+"_DIR"])
				for x in ("CC", "CXX"):
					if x in d:	d[x] = "%s %s" % (s.lower(), d[x])
					else:		d[x] = s.lower()
			else:
				for y in ("_PATH", "_DIR"):
					if s+y in d:
						del d[s+y]
		
		path = filter(None, path)
		d["PATH"] = ":".join(path)
		self.fetchables = pkg.fetchables[:]
		d["A"] = ' '.join(map(lambda x: x.filename, self.fetchables))
		d["XARGS"] = xargs

		self.env = d
		self.eclass_cache = eclass_cache
		self.fetcher = fetcher
		self.bashrc = d.get("bashrc", [])
		self.pkg = pkg
		self.eapi = pkg.eapi
		for k,v in self.env.items():
			if not isinstance(v, basestring):
				del self.env[k]


	def _prep_ebd(self, ebd, phase):
		ebd.write("process_ebuild "+phase)
		if not ebd.send_env(self.env):
			raise GenericBuildError(phase + ": Failed sending env to the ebd processor")
		ebd.set_sandbox_state(self.sandbox)
		if self.logging and not ebd.set_logging(self.logging):
			raise GenericBuildError(phase + ": Failed commanding ebd to log to " + self.logging)


	def setup(self):
		# ensure dirs.
		for k, text in (("HOME", "home"), ("T", "temp"), ("WORKDIR", "work"), ("D", "image")):
			if not ensure_dirs(self.env[k], mode=0770, gid=portage_gid):
				raise FailedDirectory(self.env[k], "required: %s directory" % text)
		if self.distcc:
			for p in ("", "/lock", "/state"):
				if not ensure_dirs(os.path.join(self.env["DISTCC_DIR"], p), mode=02775, gid=portage_gid):
					raise FailedDirectory(os.path.join(self.env["DISTCC_DIR"], p), "failed creating needed distcc directory")
		if self.ccache:
			# yuck.
			st = None
			try:	st = os.stat(self.env["CCACHE_DIR"])
			except OSError:
				st = None
				if not ensure_dirs(self.env["CCACHE_DIR"], mode=02775, gid=portage_gid):
					raise FailedDirectory(self.env["CCACHE_DIR"], "failed creation of ccache dir")
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
								raise FailedDirectory(self.env["CCACHE_DIR"], "failed changing ownership for CCACHE_DIR")
							if 0 != spawn_bash("find . -type d | %s chmod 02775" % xargs):
								raise FailedDirectory(self.env["CCACHE_DIR"], "failed correcting perms for CCACHE_DIR")
						finally:
							os.chdir(cwd)
				except OSError:
					raise FailedDirectory(self.env["CCACHE_DIR"], "failed ensuring perms/group owner for CCACHE_DIR")

		if self.logging and not ensure_dirs(os.path.dirname(self.env["PORT_LOGFILE"]), mode=02770, gid=portage_gid):
			raise FailedDirectory(self.env["PORT_LOGFILE"], "failed ensuring PORT_LOGDIR as 02770 and %i" % portage_gid)

		if len(self.files):
			self.env["DISTDIR"] = normpath(os.path.join(self.builddir, "distdir"))+"/"

			try:
				if os.path.exists(self.env["DISTDIR"]):
					if os.path.isdir(self.env["DISTDIR"]) and not os.path.islink(self.env["DISTDIR"]):
						shutil.rmtree(self.env["DISTDIR"])
					else:
						os.unlink(self.env["DISTDIR"])

			except OSError, oe:
				raise FailedDirectory(self.env["DISTDIR"], "failed removing existing file/dir/link at: exception %s" % oe)
				
			if not ensure_dirs(self.env["DISTDIR"], mode=0770, gid=portage_gid):
				raise FailedDirectory(self.env["DISTDIR"], "failed creating distdir symlink directory")

			try:
				for src, dest in [(k, os.path.join(self.env["DISTDIR"], v.filename)) for (k,v) in self.files.items()]:
					os.symlink(src,dest)

			except OSError, oe:
				raise GenericBuildError("Failed symlinking in distfiles for src %s -> %s: %s" % (src, dest, str(oe)))
		
		ebd = request_ebuild_processor(userpriv=False, sandbox=self.sandbox)
		try:
			self._prep_ebd(ebd, "setup")
			ebd.write("start_processing")
			if not ebd.generic_handler(additional_commands={"request_inherit":post_curry(ebd.__class__._inherit, self.eclass_cache),
				"request_profiles":self._request_bashrcs}):
				raise GenericBuildError("setup: Failed building (False/0 return from handler)")
		except Exception, e:
			# regardless of what occured, we kill the processor.
			ebd.shutdown_processor()
			release_ebuild_processor(ebd)
			# either we know what it is, or it's a shutdown.  re-raise
			if isinstance(e, (SystemExit, GenericBuildError)):
				raise
			# wrap.
			raise GenericBuildError("setup: Caught exception while building: " + str(e))

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
			self._prep_ebd(ebd, phase)
			ebd.write("start_processing")
			if not ebd.generic_handler():
				raise GenericBuildError(phase + ": Failed building (False/0 return from handler)")

		except Exception, e:
			ebd.shutdown_processor()
			release_ebuild_processor(ebd)
			if isinstance(e, (SystemExit, GenericBuildError)):
				raise
			raise GenericBuildError(phase + ": Caught exception while building: %s" % e)

		release_ebuild_processor(ebd)
		return True


	def configure(self):
		if self.eapi > 0:
			return self._generic_phase("configure", True, True, False)
		return True


	unpack = pretty_docs(
		post_curry(_generic_phase, "unpack", True, True, False),
		"run the unpack phase")
	compile = post_curry(_generic_phase, "compile", True, True, False)
	test = post_curry(_generic_phase, "test", True, True, False)
	

	def install(self):
		if self.fakeroot:
			return self._generic_phase("install", True, False, True)
		else:
			return self._generic_phase("install", True, True, False)


	def test(self):
		if not self.run_test:
			return True
		return self._generic_phase("test", True, True, False)


	def clean(self):
		if not os.path.exists(self.builddir):
			return True
		try:
			shutil.rmtree(self.builddir)
		except OSError, oe:
			raise GenericBuildError("clean: Caught exception while cleansing: %s" % oe)
		return True

	def finalize(self):
		return self._built_class(self.pkg, scan(self.env["IMAGE"], offset=self.env["IMAGE"]), environment=local_source(os.path.join(self.env["T"], "environment")))

