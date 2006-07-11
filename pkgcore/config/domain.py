# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base class to derive from for domain objects

Bit empty at the moment
"""
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.repository:multiplex")

# yes this is basically empty.  will fill it out as the base is better identified.

class domain(object):
	
	def __getattr__(self, attr):
		if attr == "all_repos":
			a = self.repos = multiplex.tree(*self.repos)
		elif attr == "all_vdbs":
			a = self.all_vdbs = multiplex.tree(*self.vdb)
		else:
			raise AttributeError(attr)
		return a
