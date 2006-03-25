# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.config import profiles
import os, logging
from pkgcore.util.lists import unique
from pkgcore.util.file import iter_read_bash, read_dict, read_bash_dict
from pkgcore.util.currying import pre_curry
from pkgcore.package.atom import atom
from pkgcore.config.basics import list_parser
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from itertools import imap

# Harring sez-
# This should be implemented as an auto-exec config addition.

class OnDiskProfile(profiles.base):
	positional = ("base_repo","profile")
	required = ("base_repo", "profile")
	section_ref = ("base_repo")

	def __init__(self, base_repo, profile, incrementals=None):

		if incrementals is None:
			incrementals = []

		self.basepath = os.path.join(base_repo.base,"profiles")

		dep_path = os.path.join(self.basepath, profile, "deprecated")
		if os.path.isfile(dep_path):
			logger.warn("profile '%s' is marked as deprecated, read '%s' please" % (profile, dep_path))
		del dep_path

		parents = [None]
		stack = [os.path.join(self.basepath, profile.strip())]
		idx = 0

		while len(stack) > idx:
			parent, trg = parents[idx], stack[idx]

			if not os.path.isdir(trg):
				if parent:
					raise profiles.ProfileException("%s doesn't exist, or isn't a dir, referenced by %s" % (trg, parent))
				raise profiles.ProfileException("%s doesn't exist, or isn't a dir" % trg)

			fp = os.path.join(trg, "parent")
			if os.path.isfile(fp):
				l = []
				try:
					f = open(fp,"r")
				except (IOError, OSError):
					raise profiles.ProfileException("failed reading parent from %s" % path)
				for x in f:
					x = x.strip()
					if x.startswith("#") or x == "":
						continue
					l.append(x)
				f.close()
				l.reverse()
				for x in l:
					stack.append(os.path.abspath(os.path.join(trg, x)))
					parents.append(trg)
				del l
			
			idx+=1

		del parents

		def loop_iter_read(files, callable=iter_read_bash):
			for fp in files:
				if os.path.exists(fp):
					try: 
						yield fp, callable(fp)
					except (OSError, IOError), e:
						raise profiles.ProfileException("failed reading '%s': %s" % (e.filename, str(e)))


		# build up visibility limiters.
		stack.reverse()
		pkgs = set()
		for fp, i in loop_iter_read(os.path.join(prof, "packages") for prof in stack):
			for p in i:
				if p[0] == "-":
					try:	pkgs.remove(p[1:])
					except KeyError:
						logger.warn("%s is reversed in %s, but isn't set yet!" % (p[1:], fp))
				else:	pkgs.add(p)

		visibility = []
		sys = []
		for p in pkgs:
			if p[0] == "*":
				# system set.
				sys.append(atom(p[1:]))
			else:
				# note the negation.  this means cat/pkg matchs, but ver must not, else it's masked.
				visibility.append(atom(p, negate_vers=True))
		del pkgs
		self.sys = sys
		self.visibility = visibility

		use_mask = set()
		for fp, i in loop_iter_read(os.path.join(prof, "use.mask") for prof in stack):
			for p in i:
				if p[0] == "-":
					try:	use_mask.remove(p[1:])
					except KeyError:
						logger.warn("%s is reversed in %s, but isn't set yet!" % (p[1:], fp))
				else:
					use_mask.add(p)

		self.use_mask = list(use_mask)
		del use_mask
		self.bashrc = map(local_source, filter(os.path.exists, imap(lambda x: os.path.join(x, "profile.bashrc"), stack)))

		maskers = []
		for fp, i in loop_iter_read(os.path.join(prof, "package.mask") for prof in stack + [self.basepath]):
			for p in i:
				if p[0] == "-":
					try:	maskers.remove(p[1:])
					except KeyError:
						logger.warn("%s is reversed in %s, but isn't set yet!" % (p[1:], fp))
				else:	maskers.extend([p])

		self.maskers = map(atom,maskers)
		del maskers

		d = {}
		for fp, dc in loop_iter_read((os.path.join(prof, "make.defaults") for prof in stack), 
			lambda x:read_bash_dict(x, vars_dict=ProtectedDict(d))):
			for k,v in dc.items():
				# potentially make incrementals a dict for ~O(1) here, rather then O(N)
				if k in incrementals:
					v = list_parser(dc[k])
					if k in d:		d[k] += v
					else:				d[k] = v
				else:					d[k] = v

		d.setdefault("USE_EXPAND",'')
		if isinstance(d["USE_EXPAND"],str):
			d["USE_EXPAND"] = d["USE_EXPAND"].split()
		for u in d["USE_EXPAND"]:
			u2 = u.lower()+"_"
			if u in d:
				d["USE"].extend(map(u2.__add__, d[u].split()))
				del d[u]

		# collapsed make.defaults.  now chunkify the bugger.
		self.conf = d

	def cleanse(self):
		del self.visibility
		del self.system
		del self.use_mask
		del self.maskers

#	def get_path(self, bashrc):
#		fp = os.path.join(self.basepath, bashrc)
#		if not os.path.exists(fp):
#			return None
#		return fp
#	
#	def get_data(self, bashrc):
#		fp = self.get_path(bashrc)
#		if fp == None:
#			return None
#		try:
#			f = open(fp, "r")
#			d = f.read()
#			f.close()
#		except OSError:
#			return None
#		return d
