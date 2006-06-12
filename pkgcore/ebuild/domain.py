# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os
import pkgcore.config.domain
from pkgcore.util.compatibility import any, all
from pkgcore.restrictions.collapsed import DictBased
from pkgcore.restrictions import packages, values
from pkgcore.util.file import iter_read_bash
from pkgcore.package.atom import atom
from pkgcore.repository import multiplex, visibility
from pkgcore.restrictions.values import StrGlobMatch, ContainmentMatch
from pkgcore.util.lists import stable_unique, unstable_unique
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.config.errors import BaseException

class MissingFile(BaseException):
	def __init__(self, file, setting):
		self.file, self.setting = file, setting
	def __str__(self):
		return "setting %s points at %s, which doesn't exist." % (self.setting, self.file)

class Failure(BaseException):
	def __init__(self, text):
		self.text = text
	def __str__(self):
		return "domain failure: %s" % self.text


def split_atom(inst):
	if len(inst.restrictions) > 3:
		a = packages.AndRestriction(*inst.restrictions[2:])
	elif len(inst.restrictions) == 3:
		a = inst.restrictions[2]
	else:
		a = []
	return inst.category + "/" + inst.package, a

def get_key_from_package(collapsed_inst, pkg):
	return pkg.category + "/" + pkg.package

def package_keywords_splitter(val):
	v = val.split()
	return atom(v[0]), stable_unique(v[1:])


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
#
# note also, that this is rather ebuild centric.  it shouldn't be, and should be redesigned to be a seperation of
# configuration instantiation manglers, and then the ebuild specific chunk (which is selected by config)
# ~harring


def filter_negations(setting, orig_list):
	l = set()
	for x in orig_list:
		if x.startswith("-"):
			if x.startswith("-*"):
				l.clear()
			else:
				if len(x) == 1:
					raise Failure("negation of a setting in '%s', but name negated isn't completed-" % (k, v))
				x = x[1:]
				if x in l:
					l.remove(x)
		else:
			l.add(x)
	return l

def generate_masking_restrict(masks):
	# if it's masked, it's not a match
	return DictBased((split_atom(x) for x in masks), get_key_from_package, negate=True)

def generate_unmasking_restrict(unmasks):
	return DictBased((split_atom(x) for x in unmasks), get_key_from_package)


class domain(pkgcore.config.domain.domain):
	def __init__(self, incrementals, root, profile, repositories, vdb, **settings):
		# voodoo, unfortunately (so it goes)
		# break this up into chunks once it's stabilized (most of code here has already, but still more to add)
		pkg_maskers, pkg_unmaskers, pkg_keywords, pkg_license = list(profile.maskers), [], [], []

		for key, val, action in (("package.mask", pkg_maskers, atom), ("package.unmask", pkg_unmaskers, atom),
			("package.keywords", pkg_keywords, package_keywords_splitter),
			("package.license", pkg_license, package_keywords_splitter)):

			if key in settings:
				for fp in settings[key]:
					# unecessary stating.
					if os.path.exists(fp):
						try:
							val.extend(action(x) for x in iter_read_bash(fp))
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

		vfilter = packages.AndRestriction(finalize=False, inst_caching=False)
		r = None
		if pkg_maskers:
			r = generate_masking_restrict(pkg_maskers)
		if pkg_unmaskers:
			if r is None:
				# unmasking without masking... 'k (wtf?)
				r = generate_unmasking_restrict(pkg_unmaskers)
			else:
				r = packages.OrRestriction(r, generate_unmasking_restrict(pkg_unmaskers), disable_inst_caching=True)
		if r:
			vfilter.add_restriction(r)
		del pkg_unmaskers, pkg_maskers
		
		use, license, default_keywords = [], [], []

		master_license = []
		for k,v in (("USE", use), ("ACCEPT_KEYWORDS", default_keywords), ("ACCEPT_LICENSE", master_license)):
			if k not in settings:
				raise Failure("No %s setting detected from profile, or user config" % k)
			v.extend(filter_negations(k, settings[k]))
			settings[k] = v

		if "ARCH" not in settings:
			raise Failure("No ARCH setting detected from profile, or user config")

		arch = settings["ARCH"]

		# ~amd64 -> [amd64, ~amd64]
		for x in default_keywords[:]:
			if x.startswith("~"):
				default_keywords.append(x.lstrip("~"))
		default_keywords = unstable_unique(default_keywords + [arch])
		
		keywords_filter = self.generate_keywords_filter(arch, default_keywords, pkg_keywords, 
			already_unstable=("~%s" % arch.lstrip("~") in default_keywords))
		vfilter.add_restriction(keywords_filter)
		del keywords_filter
		# we can finally close that fricking "DISALLOW NON FOSS LICENSES" bug via this >:)
		if master_license:
			if license:
				r = packages.OrRestriction(negate=True)
				r.add_restriction(packages.PackageRestriction("license", ContainmentMatch(*master_license)))
				r.add_restriction(DictBased(license, get_key_from_package))
				vfilter.add_restriction(r)
			else:
				vfilter.add_restriction(packages.PackageRestriction("license", ContainmentMatch(*master_license)))
		elif license:
			vfilter.add_restriction(DictBased(license, get_key_from_package))

		del master_license, license
		
		# if it's made it this far...
		
		settings["ROOT"] = root
		# this should be handled via another means
		if "default" in settings:
			del settings["default"]
		self.settings = settings

		if profile.get_path is None and profile.get_data is None:
			raise Failure("profile instance '%s' lacks a usable ebd_data_source method" % profile)
		bashrc = list(profile.bashrc)

		if "bashrc" in self.settings:
			for input in self.settings['bashrc']:
				source = local_source(input)
				# this is currently local-only so a get_path check is ok
				# TODO make this more general
				if source.get_path() is None:
					raise Failure(
						'user-specified bashrc %r does not exist' %	input)
				bashrc.append(source)

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
							pargs.append(getattr(self, x))
				except AttributeError, ae:
					raise Failure("failed configuring repo '%s': configurable missing: %s" % (repo, ae))
				self.repos.append(repo.configure(*pargs))
			else:
				self.repos.append(repo)
			# do this once at top level instead.
		self.repos = [visibility.filterTree(t, vfilter, True) for t in self.repos]
		if profile.virtuals:
			self.repos = [multiplex.tree(t, profile.virtuals(t)) for t in self.repos]
		self.vdb = vdb


	def generate_keywords_filter(self, arch, default_keys, pkg_keywords, already_unstable=False):
		"""generates a restrict that matches true iff the keywords are allowed"""
		if not pkg_keywords:
			return packages.PackageRestriction("keywords", values.ContainmentMatch(*default_keys))
		
		keywords_filter = {}

		# save on instantiation caching/creation costs.
		if already_unstable:
			unstable_restrict = ContainmentMatch(*default_keys)
		else:
			unstable_restrict = ContainmentMatch("~%s" % arch.lstrip("~"), *default_keys)
		unstable_pkg_restrict = packages.PackageRestriction("keywords", unstable_restrict)
		default_restrict = ContainmentMatch(*default_keys)
		default_keys = set(default_keys)
		
		for pkgatom, vals in pkg_keywords:
			if not vals:
				# if we already are unstable, no point in adding this exemption
				if already_unstable:
					continue
				r = unstable_pkg_restrict
			else:
				per, glob, negated = [], [], []
				for x in vals:
					s = x.lstrip("-")
					negate = x.startswith("-")
					if "~*" == s:
						if negate:
							raise Failure("can't negate -~* keywords")
						glob.append(StrGlobMatch("~"))
					elif "*" == s:
						if negate:
							raise Failure("can't -* keywords")
						# stable only, exempt unstable
						glob.append(StrGlobMatch("~", negate=True))
					elif negate:
						negated.append(s)
					else:
						per.append(s)
				r = values.OrRestriction(inst_caching=False)
				if per:
					r.add_restriction(ContainmentMatch(*per))
				if glob:
					r.add_restriction(*glob)
				if negated:
					if r.restrictions:
						r.add_restriction(values.ContainmentMatch(*default_keys.difference(negated)))
					else:
						# strictly a limiter of defaults.  yay.
						r = values.ContainmentMatch(*default_keys.difference(negated))
				else:
					r.add_restriction(default_restrict)
				r = packages.PackageRestriction("keywords", r)
			keywords_filter[pkgatom] = r

		keywords_filter["__DEFAULT__"] = packages.PackageRestriction("keywords", default_restrict)
		def redirecting_splitter(collapsed_inst, pkg):
			key = get_key_from_package(collapsed_inst, pkg)
			if key not in collapsed_inst.restricts_dict:
				return "__DEFAULT__"
			return key

		return DictBased(keywords_filter.iteritems(), redirecting_splitter)
