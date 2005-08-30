# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: metadata.py 1944 2005-08-30 02:02:12Z ferringb $

import os, stat
import flat_hash
import cache_errors
from portage.ebuild import eclass_cache 
from template import reconstruct_eclasses, serialize_eclasses
from portage.util.mappings import ProtectedDict

# store the current key order *here*.
class database(flat_hash.database):
	complete_eclass_entries = False
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE')

	autocommits = True

	def __init__(self, *args, **config):
		super(database, self).__init__(*args, **config)
		self.ec = eclass_cache.cache(self.location)

	def __getitem__(self, cpv):
		d = flat_hash.database.__getitem__(self, cpv)

		if "_eclasses_" not in d:
			if "INHERITED" in d:
				d["_eclasses_"] = self.ec.get_eclass_data(d["INHERITED"].split(), from_master_only=True)
				del d["INHERITED"]
		else:
			d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"])

		return d


	def _setitem(self, cpv, values):
		values = ProtectedDict(values)
		
		# hack.  proper solution is to make this a __setitem__ override, since template.__setitem__ 
		# serializes _eclasses_, then we reconstruct it.
		if "_eclasses_" in values:
			values["INHERITED"] = ' '.join(reconstruct_eclasses(cpv, values["_eclasses_"]).keys())
			del values["_eclasses_"]

		flat_hash.database._setitem(self, cpv, values)
