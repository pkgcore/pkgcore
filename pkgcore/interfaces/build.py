# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# metaclasses, 101.  metaclass gets called to instantiate a class (creating a class instance).
# effectively, __metaclass__ controls how that class is converted from a definition, to an object, with the
# object being used to create instances of that class.
# note python doesn't exactly have definitions, just executions, but analogy is close enough :P

from pkgcore.util.dependant_methods import ForcedDepends

__all__ = ["base", "FailedDirectory", "GenericBuildError", "errors"]

class base(object):
	stage_depends = {"setup":"fetch",		"unpack":"setup",
					"configure":"unpack",	"compile":"configure", "test":"compile",
					"install":"test", 	"finalize":"install"}

	__metaclass__ = ForcedDepends

	def setup(self):		return True
	def unpack(self):		return True
	def configure(self):	return True
	def compile(self):		return True
	def test(self):			return True
	def install(self):		return True
	def finalize(self):		return True
	def cleanup(self):		return True

	def fetch(self):
		if not "files" in self.__dict__:
			self.files = {}

		# this is being anal, but protect against pkgs that don't collapse common uri down to a single file.
		gotten_fetchables = set(x.filename for x in self.files.values())
		for x in self.fetchables:
			if x.filename in gotten_fetchables:
				continue
			fp = self.fetcher(x)
			if fp is None:
				return False
			self.files[fp] = x
			gotten_fetchables.add(x.filename)

		return True

class BuildError(Exception): pass

class FailedDirectory(BuildError):
	def __init__(self, path, text):	self.path, self.text = path, text
	def __str__(self):	return "failed creating/ensuring dir %s: %s" % (self.path, self.text)

class GenericBuildError(BuildError):
	def __init__(self, err):	self.err = str(err)
	def __str__(self):	return "Failed build operation: " + self.err

errors = (FailedDirectory, GenericBuildError)
