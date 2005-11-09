# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: central.py 2272 2005-11-10 00:19:01Z ferringb $

import errors, new
from portage.const import CONF_DEFAULTS
from portage.util.modules import load_attribute
from cparser import CaseSensitiveConfigParser as ConfigParser
from portage.util.mappings import LazyValDict
from portage.util.currying import pre_curry

class config:
	"""Central configuration manager.
	collapses configurations, instantiates objects dependant on section definitions (mislabled conf_defaults), and 
	a ConfigParser (or object with such an api) that is passed in.

	see conf_default_types for explanation of default sections and capabilities
	"""

	def __init__(self, cparser, conf_defaults=CONF_DEFAULTS):
		self._cparser = cparser
		self.type_handler = load_conf_definitions(conf_defaults)
		self.type_conversions = {}
		# add auto exec shit
		# weakref .instantiated?
		self.instantiated = {}
		for t in self.type_handler:
			for x in ("required", "incrementals", "defaults", "section_ref", "positional"):
				self.type_handler[t][x] = tuple(list_parser(self.type_handler[t].get(x,"")))
				
			conversions = {}
			for x,f in (("list", list_parser), ("str", str_parser), ("bool", bool_parser)):
				if x in self.type_handler[t]:
					for y in list_parser(self.type_handler[t][x]):
						conversions[y] = f
					del self.type_handler[t][x]

			if "positional" in self.type_handler[t]:
				for x in self.type_handler[t]["positional"]:
					if x not in self.type_handler[t]["required"]:
						raise errors.BrokenSectionDefinition(t, "position '%s' is not listed in required" % x)

			conversions["_default_"] = str_parser
			self.type_conversions[t] = conversions

			# cleanup, covering ass of default conf definition author (same parsing rules applied to conf, applied to default)			
			# without this, it's possible for a section definitions conf to make errors appear via defaults in a config, if
			# the section definition is fscked.
			# work out an checkup of defaults + conversions for config definition, right now we allow that possibility
			# to puke while inspecting user config (the passed in cparser)
#			for k,v in self.type_handler[t].items():
#				try:
#					self.type_handler[t][k] = str_parser(v)
#				except errors.QuoteInterpretationError, qe:
#					qe.var = v
#					raise qe
			setattr(self, t, LazyValDict(pre_curry(self.sections, t), self.instantiate_section))

	def collapse_config(self, section, verify=True):
		"""collapse a section's config down to a dict for use in instantiating that section.
		verify controls whether sanity checks specified by the section type are enforced.
		required and section_ref fex, are *not* verified if this is False."""

		if not self._cparser.has_section(section):
			raise KeyError("%s not a valid section" % section)
		if not self._cparser.has_option(section, "type"):
			raise errors.UnknownTypeRequired("Not set")
		type = str_parser(self._cparser.get(section, "type"))
		if not self.type_handler.has_key(type):
			raise errors.UnknownTypeRequired(type)

		slist = [section]

		# first map out inherits.
		i=0;
		while i < len(slist):
			if self._cparser.has_option(slist[i], "inherit"):
				slist.extend(list_parser(self._cparser.get(slist[i], "inherit")))
				if not self._cparser.has_section(slist[i]):
					raise errors.InheritError(slist[i-1], slist[i])
			i+=1
		# collapse, honoring incrementals.
		# remember that inherit's are l->r.  So the slist above works with incrementals,
		# and default overrides (doesn't look it, but it does. tree isn't needed, list suffices)
		incrementals = self.type_handler[type]["incrementals"]
		conversions = self.type_conversions[type]

		cleanse_inherit = len(slist) > 1

		d={}
		default_conversion = conversions["_default_"]
		while len(slist):
			d2 = dict(self._cparser.items(slist[-1]))
			# conversions, baby.
			for x in d2.keys():
				try:
					# note get ain't a tertiary op.  so, this is the same as the equivalent contains/exec else
					# find default/exec struct.
					d2[x] = conversions.get(x, default_conversion)(d2[x])
				except errors.QuoteInterpretationError, qe:
					qe.var = v;
					raise qe
			for x in incrementals:
				if x in d2 and x in d:
					d2[x] = d[x] + d2[x]

			d.update(d2)
			slist.pop(-1)

		if cleanse_inherit:
			del d["inherit"]

		d["type"] = type
		default_conversion = conversions["_default_"]
		for x in self.type_handler[type]["defaults"]:
			if x not in d:
				if x == "label":
					d[x] = section
					continue
				# XXX yank the checks later, see __init__ for explanation of default + conversions + section conf possibility
				try:
					d[x] = conversions.get(x, default_conversion)(self.type_handler[type][x])
				except errors.QuoteInterpretationError, qe:
					qe.var = v;
					raise qe

		if verify:
			for var in self.type_handler[type]["required"]:
				if var not in d:
					raise errors.RequiredSetting(type, section, var)
			for var in self.type_handler[type]["section_ref"]:
				if var in d:
					if isinstance(d[var], list):
						for sect_label in d[var]:
							if not self._cparser.has_section(sect_label):
								raise errors.SectionNotFound(section, var, sect_label)
					elif not self._cparser.has_section(d[var]):
						raise errors.SectionNotFound(section, var, sect_label)
		
		return d

	def instantiate_section(self, section, conf=None, allow_reuse=True):
		"""make a section config into an actual object.
		if conf is specified, allow_reuse is forced to false.
		if conf isn't specified, it's pulled via collapse_config
		allow_reuse is used for controlling whether existing instantiations of that section can be reused or not."""
		if not self._cparser.has_section(section):
			raise KeyError("%s not a valid section" % section)
		if conf == None:
			if section in self.instantiated:
				return self.instantiated[section]
			conf = self.collapse_config(section)
		else:
			allow_reuse = False

		if "type" not in conf:
			raise errors.UnknownTypeRequired(section)
		type = conf["type"]
		del conf["type"]
		
		if "class" not in conf:
			raise errors.ClassRequired(section, type)
		cls_name = conf["class"]
		del conf["class"]

		callable_obj = load_attribute(cls_name)
		if not callable(callable_obj):
			raise errors.InstantiationError(cls_name, [], conf,
				TypeError("%s is not a class/callable" % type(callable_obj)))

		if "instantiate" in self.type_handler[type]:
			inst = load_attribute(self.type_handler[type]["instantiate"])
			if not callable(inst):
				raise errors.InstantiationError(self.type_handler[type]["instantiate"], [], conf,
					TypeError("%s is not a class/callable" % type(inst)))
		else:
			inst = None
			# instantiate all section refs.
			for var in self.type_handler[type]["section_ref"]:
				if var in conf:
					if isinstance(conf[var], list):
							for x in range(0, len(conf[var])):
								conf[var][x] = self.instantiate_section(conf[var][x])
					else:
						conf[var] = self.instantiate_section(conf[var])
			pargs = []
			for var in self.type_handler[type]["positional"]:
				pargs.append(conf[var])
				del conf[var]
		try:
			if inst != None:	
				obj=inst(self, callable_obj, section, conf)
			else:		
				obj=callable_obj(*pargs, **conf)
		except Exception, e:
			if isinstance(e, RuntimeError) or isinstance(e, SystemExit) or isinstance(e, errors.InstantiationError):
				raise
			#else wrap and chuck.
			if not __debug__:
				raise errors.InstantiationError(cls_name, [], conf, e)
			raise
		if obj == None:
			raise errors.InstantiationError(cls_name, [], conf, errors.NoObjectReturned(cls_name))

		if allow_reuse:
			self.instantiated[section] = obj

		return obj

	def sections(self, type=None):
		if type==None:
			return self._cparser.sections()
		l=[]
		for x in self.sections():
			if self._cparser.has_option(x, "type") and self._cparser.get(x,"type") == type:
				l.append(x)
		return l

def load_conf_definitions(loc):
	c = ConfigParser()
	c.read(loc)
	d = {}
	for x in c.sections():
		d[x] = dict(c.items(x))
	del c
	return d


def list_parser(s):
	"""split on whitespace honoring quoting for new tokens"""
	l=[]
	i = 0
	e = len(s)
	while i < e:
		if not s[i].isspace():
			if s[i] in ("'", '"'):
				q = i
				i += 1
				while i < e and s[i] != s[q]:
					if s[i] == '\\':
						i+=2
					else:
						i+=1
				if i >= e:
					raise errors.QuoteInterpretationError(s)
				l.append(s[q+1:i])
			else:
				start = i
				while i < e and not (s[i].isspace() or s[i] in ("'", '"')):
					if s[i] == '\\':
						i+=2
					else:
						i+=1
				if i < e and s[i] in ("'", '"'):
					raise errors.QuoteInterpretationError(s)
				l.append(s[start:i])
		i+=1
	return l

def str_parser(s):
	"""yank leading/trailing whitespace and quotation, along with newlines"""
	i=0
	l = len(s)
	while i < l and s[i].isspace():
		i+=1
	if i < l and s[i] in ("'",'"'):
		i+=1
	e=l
	while e > i and s[e - 1].isspace():
		e-=1
	if e > i and s[e - 1] in ("'", '"'):
		e-=1
	if e > i:
		s=s[i:e]
		i = 0; e = len(s) - 1
		while i < e:
			if s[i] in ("\n", "\t"):
				s[i] = ' '
			i+=1
		return s
	else:
		return ''
	
def bool_parser(s):
	s = str_parser(s).lower()
	if s in ("", "no", "false", "0"):
		return False
	return True
