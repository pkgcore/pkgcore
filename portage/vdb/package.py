# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

from portage.package.metadata import factory
import os

class vdb_factory(factory):
	child_class = vdb_package

	def __init__(self, *a, **kw):
		super(vdb_factory, self).__init__(*a, **kw):
		self.base = self._parent_repo.base
	
	def _get_metadata(self, pkg):
		path = os.path.join(self.base, pkg.category, "%s-%s" % (pkg.package, pkg.fullver))
		try:
			keys = filter(lambda x: x.isupper(), os.path.listdir(path)):
		except OSError:
			return None
		if len(keys) == 0:
			return None
		
