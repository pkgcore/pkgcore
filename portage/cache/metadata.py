# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import os, stat
import fs_template
import cache_errors
from portage.ebuild import eclass_cache 
from template import reconstruct_eclasses, serialize_eclasses

# store the current key order *here*.
class database(fs_template.FsBased):
	complete_eclass_entries = False
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE')

	autocommits = True

	def __init__(self, *args, **config):
		if "unused_padding" in config:
			self.unused_padding = int(config["unused_padding"])
			del config["unused_padding"]
		else:
			self.unused_padding = 0

		super(database,self).__init__(*args, **config)
		location = self.location
		self.location = os.path.join(self.location, "metadata/cache")
#			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if len(self._known_keys) > len(self.auxdbkey_order):
			raise Exception("less ordered keys then auxdbkeys")
		if not os.path.exists(self.location):
			self._ensure_dirs()
		self.ec = eclass_cache.cache(location)

	def __getitem__(self, cpv):
		d = {}
		try:
			myf = open(os.path.join(self.location, cpv),"r")
			for k,v in zip(self.auxdbkey_order, myf):
				d[k] = v.rstrip("\n")
		except (OSError, IOError),e:
			if isinstance(e,IOError) and e.errno == 2:
				raise KeyError(cpv)
			raise cache_errors.CacheCorruption(cpv, e)
		if "_eclasses_" not in d:
			if "INHERITED" in d:
				d["_eclasses_"] = self.ec.get_eclass_data(d["INHERITED"].split(), from_master_only=True)
				del d["INHERITED"]
		else:
			d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"])

		try:		d["_mtime_"] = os.lstat(os.path.join(self.location, cpv)).st_mtime
		except OSError, e:raise cache_errors.CacheCorruption(cpv, e)
		return d


	def _setitem(self, cpv, values):
		s = cpv.rfind("/")
		fp=os.path.join(self.location,cpv[:s],".update.%i.%s" % (os.getpid(), cpv[s+1:]))
		try:	myf=open(fp, "w")
		except (OSError, IOError), e:
			if e.errno == 2:
				try:
					self._ensure_dirs(cpv)
					myf=open(fp,"w")
				except (OSError, IOError),e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

		
#			try:	
#				s = os.path.split(cpv)
#				if len(s[0]) == 0:
#					s = s[1]
#				else:
#					s = s[0]
#				os._ensure_dirs(s)
#
#			except (OSError, IOError), e:

		# hack.  proper solution is to make this a __setitem__ override, since template.__setitem__ 
		# serializes _eclasses_, then we reconstruct it.
		if "_eclasses_" in values:
			values["INHERITED"] = ' '.join(reconstruct_eclasses(cpv, values["_eclasses_"]).keys())
			del values["_eclasses_"]

		myf.writelines(values.get(x,"")+"\n" for x in self.auxdbkey_order)
		myf.write("\n"*self.unused_padding)
		myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])
		#update written.  now we move it.
		new_fp = os.path.join(self.location,cpv)
		try:	os.rename(fp, new_fp)
		except (OSError, IOError), e:
			os.remove(fp)
			raise cache_errors.CacheCorruption(cpv, e)


	def _delitem(self, cpv):
		try:
			os.remove(os.path.join(self.location,cpv))
		except OSError, e:
			if e.errno == 2:
				raise KeyError(cpv)
			else:
				raise cache_errors.CacheCorruption(cpv, e)


	def has_key(self, cpv):
		return os.path.exists(os.path.join(self.location, cpv))


	def iterkeys(self):
		"""generator for walking the dir struct"""
		dirs = [self.location]
		len_base = len(self.location)
		while len(dirs):
			for l in os.listdir(dirs[0]):
				if l.endswith(".cpickle"):
					continue
				p = os.path.join(dirs[0],l)
				st = os.lstat(p)
				if stat.S_ISDIR(st.st_mode):
					dirs.append(p)
					continue
				yield p[len_base+1:]
			dirs.pop(0)

