# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: domain.py 2196 2005-10-26 22:23:18Z ferringb $

import os
from portage.restrictions.collapsed import DictBased
from portage.restrictions import packages, values #import OrRestriction, AndRestriction, PackageRestriction
from errors import BaseException
from portage.util.file import iter_read_bash
from portage.package.atom import atom
from portage.repository.visibility import filterTree
from portage.restrictions.values import StrGlobMatch, StrExactMatch, ContainmentMatch
from portage.util.currying import post_curry
from portage.util.lists import unique
from portage.util.mappings import ProtectedDict
from itertools import imap
from portage.protocols.data_source import local_source

class MissingFile(BaseException):
	def __init__(self, file, setting):	self.file, self.setting = file, setting
	def __str__(self):						return "setting %s points at %s, which doesn't exist." % (self.setting, self.file)

class Failure(BaseException):
	def __init__(self, text):	self.text = text
	def __str__(self):			return "domain failure: %s" % self.text


def split_atom(inst):
	return inst.category + "/" + inst.package, inst.restrictions[2:]
	
def get_key_from_package(pkg):
	return pkg.category + "/" + pkg.package

def package_keywords_splitter(val):
	v=val.split()
	return atom(v[0]), unique(v[1:])


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
#
# note also, that this is rather ebuild centric.  it shouldn't be, and should be redesigned to be a seperation of 
# configuration instantiation manglers, and then the ebuild specific chunk (which is selected by config)
# ~harring

class domain:
	def __init__(self, incrementals, root, profile, repositories, vdb, **settings):
		# voodoo, unfortunately (so it goes)
		# break this up into chunks once it's stabilized (most of code here has already, but still more to add)
		maskers, unmaskers, keywords, license = profile.maskers[:], [], [], []
		if len(profile.visibility):
			maskers.extend(profile.visibility)

		for key, val, action in (("package.mask", maskers, atom), ("package.unmask", unmaskers, atom), 
			("package.keywords", keywords, package_keywords_splitter), ("package.license", license, package_keywords_splitter)):
			if key in settings:

				for fp in settings[key]:
					if os.path.exists(fp):
						try:  val.extend(imap(action, iter_read_bash(fp)))
						except (IOError, OSError, ValueError), e:
							raise Failure("failed reading '%s': %s" % (fp, str(e)))
					else:
						raise MissingFile(settings[key], key)
				del settings[key]

		inc_d = set(incrementals)
		for x in profile.conf.keys():
			if x in settings:
				if x in inc_d:
					# strings overwrite, lists append.
					if isinstance(settings[x], (list, tuple)):
						# profile prefixes
						settings[x] = profile.conf[x] + settings[x]
			else:
				settings[x] = profile.conf[x]
		del inc_d

		# visibility mask...
		# if ((package.mask or visibility) and not package.unmask) or not (package.keywords or accept_keywords)

		filter = packages.OrRestriction()
		masker_d = DictBased(maskers, get_key_from_package, split_atom)
		# check this.
		if len(unmaskers):
			masker_d = packages.AndRestriction(masker_d, DictBased(unmaskers, get_key_from_package, split_atom, negate=True))
		filter.add_restriction(masker_d)

		use, license, key = [], [], []

		def filter_negations(setting, orig_list):
			l = set()
			for x in orig_list:
				if x.startswith("-"):
					if x.startswith("-*"):
						l.clear()
					else:
						if len(x) == 1:
							raise Failure("negation of a setting in '%s', but name negated isn't completed-" % (k, v))
						x=x[1:]
						if x in l:	
							l.remove(x)
				else:	
					l.add(x)
			return l

		master_license = []
		for k,v in (("USE", use), ("ACCEPT_KEYWORDS", key), ("ACCEPT_LICENSE", master_license)):
			if k not in settings:
				raise Failure("No %s setting detected from profile, or user config" % k)
			v.extend(filter_negations(k, settings[k]))
			settings[k] = v

		if "ARCH" not in settings:
			raise Failure("No ARCH setting detected from profile, or user config")

		arch = settings["ARCH"]

		# faster check. if unstable arch is already in keywords, don't screw around with adding it to the filter
		ukey = "~"+arch
		ukey_check = ukey in key
		keyword_filter = []
		for a, v in keywords:
			if len(v) == 0:
				if ukey_check:	continue
				# note that we created the atom above- so we can toy with it's innards if we want. :)
				r = ContainmentMatch(ukey)
			else:
				r = values.OrRestriction()
				per_node = []
				exact = []
				for x in v:
					if x == "*":	per_node.append(StrGlobMatch("~", negate=True))
					elif x == "~*":	per_node.append(StrGlobMatch("~"))
					else:			exact.append(x)
				if len(exact):
					r.add_restriction(ContainmentMatch(*exact))
				if len(per_node):
					r.add_restriction(*exact)
			a.add_restriction(packages.PackageRestriction("keywords", r))
			keyword_filter.append(a)

		key_filter = ContainmentMatch(*key)
		if len(keyword_filter) != 0:
			filter.add_restriction(packages.OrRestriction(packages.PackageRestriction("keywords", key_filter), 
				DictBased(keyword_filter, get_key_from_package, split_atom), negate=True))
		else:
			filter.add_restriction(packages.PackageRestriction("keywords", key_filter, negate=True))
		del key_filter, keywords, keyword_filter, key, ukey, ukey_check

		# we can finally close that fricking "DISALLOW NON FOSS LICENSES" bug via this >:)
		if len(master_license) != 0:
			if len(license) != 0:
				r = packages.OrRestriction(negate=True)
				r.add_restriction(packages.PackageRestriction("license", ContainmentMatch(*master_license)))
				r.add_restriction(DictBased(license, get_key_from_package, split_atom))
				filter.add_restriction(r)
			else:
				filter.add_restriction(packages.PackageRestriction("license", ContainmentMatch(*master_license), negate=True))
		elif len(license):
			filter.add_restriction(DictBased(license, get_key_from_package, split_atom, negate=True))

		del master_license, license

		settings["ROOT"] = root
		# this should be handled via another means
		if "default" in settings:
			del settings["default"]
		self.settings = settings
			
		if profile.get_path == None and profile.get_data == None:
			raise Failure("profile instance '%s' lacks a usable ebd_data_source method" % profile)
		bashrc = profile.bashrc[:]

		if "bashrc" in self.settings:
			bashrc.extend([local_source(x) for x in self.settings["bashrc"]])

		self.settings["bashrc"] = bashrc
		
		self.repos = []
		for repo in repositories:
			if not repo.configured:
				pargs = [repo]
				try:
					for x in repo.configurables:
						if x == "domain":
							pargs.append(self)
						elif x == "settings":
							pargs.append(ProtectedDict(settings))
						elif x == "profile":
							pargs.append(profile)
						else:
							pargs.append(getattr, self, x)
				except AttributeError, ae:
					raise Failure("failed configuring repo '%s': configurable missing: %s" % (repo, ae))
				self.repos.append(repo.configure(*pargs))
			else:
				self.repos.append(repo)

		self.repos = map(post_curry(filterTree, filter, False), self.repos)
		self.vdb = vdb
