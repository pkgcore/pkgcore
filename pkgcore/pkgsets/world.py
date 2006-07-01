# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
pkgset based around loading a list of atoms from a world file
"""

from pkgcore.package.atom import atom
import pkgcore.const

class WorldFile(object):
	pkgcore_config_type = True

	def __init__(self, world_path=pkgcore.const.WORLD_FILE):
		self.path = world_path
		# note that _atoms is generated on the fly.

	def __getattr__(self, attr):
		if attr != "_atoms":
			raise AttributeError(attr)
		self._atoms = set(atom(x.strip()) for x in open(self.path, "r"))
		return self._atoms

	def __iter__(self):
		return iter(self._atoms)

	def __len__(self):
		return len(self._atoms)

	def __contains__(self, key):
		return key in self._atoms
