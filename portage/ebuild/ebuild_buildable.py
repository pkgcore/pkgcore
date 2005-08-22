import package.buildable
import os

import portage_dep, portage_util

from ebuild_internal import ebuild_handler

class ebuild_buildable(package.buildable.package):
	_metadata_pulls=("DEPEND",)

	def __init__(self, *args, **kwargs):
		super(ebuild_buildable, self).__init__(*args, **kwargs)
		dir(self)
		self.root = self._config["ROOT"]
		self._build_env = {
			"ROOT":self._config["ROOT"],	"EBUILD":self.path,
			"CATEGORY":self.category,	"PF":self.cpvstr,		
			"P":"%s-%s" % (self.package, self.version),
			"PN":self.package,		"PV":self.version,
			"PR":"-r%i" % self.revision,	"PVR":self.fullver,
			"FILESDIR":os.path.dirname(os.path.join(self.path,"files")),
			"BUILD_PREFIX":os.path.join(self._config["PORTAGE_TMPDIR"],"portage"),
			"ROOT":self._config["ROOT"],
			}

		self._build_env["BUILDDIR"]	= os.path.join(self._build_env["BUILD_PREFIX"], self._build_env["PF"])
		for x,y in (("T","temp"),("WORKDIR","work"), ("D","image")):
			self._build_env[x] = os.path.join(self._build_env["BUILDDIR"], y)

		self.URI = portage_dep.paren_reduce(self.SRC_URI)
		uf = self._config["USE"].split()
		self.ALL_URI = portage_util.flatten(portage_dep.use_reduce(self.URI,uselist=uf,matchall=True))
		self.URI = portage_util.flatten(portage_dep.use_reduce(self.URI,uselist=uf,matchall=False))


	def _setup(self):
		self.ebd = ebuild_handler(self._config)
		return self.ebd.process_phase("setup", self.path, self.root, self)

	def _fetch(self):
		return self.ebd.process_phase("fetch", self.path, self.root, self)

	def _unpack(self):
		return self.ebd.process_phase("unpack", self.path, self.root, self)

	def _configure(self):
		return True

	def _compile(self):
		return self.ebd.process_phase("compile", self.path, self.root, self)

	def _install(self):
		return self.ebd.process_phase("install", self.path, self.root, self)

	def _clean(self):
		return self.ebd.process_phase("clean", self.path, self.root, self)

