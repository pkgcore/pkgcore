# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.package.atom import atom

class WorldFile(object):
	def __init__(self, world_path):
		self.path = world_path
		# note that _atoms is generated on the fly.
			
	def __getattr__(self, attr):
		if attr != "_atoms":
			raise AttributeError(attr)
		self._atoms = set(atom(x.strip()) for x in open(self.path, "r"))
		return self._atoms
		
	def __iter__(self):
		print self._atoms
		return iter(self._atoms)
	
	def __len__(self):
		return len(self._atoms)

	def __contains__(self, key):
		return key in self._atoms
