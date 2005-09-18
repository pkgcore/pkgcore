# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

import portage.package.base
from portage.util.mappings import ImmutableDict

class built(portage.package.base.base):

	def __init__(self, pkg, contents, environment):
		for x in ("fetchables", "depends", "rdepends", "description", "license", "use", "slot", "package", "version", "category"):
			setattr(self, x, getattr(pkg, x))
		self.contents = contents
		self.bundled_data = ImmutableDict({"environment":environment})
