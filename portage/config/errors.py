# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

# potentially use an intermediate base for user config errors, seperate base for instantiation?
class BaseException(Exception):
	pass

class InheritError(BaseException):
	"""Inherit target was not found"""
	def __init__(self, baseSect, trgSect):
		self.base, self.trg = baseSect, trgSect
	def __str__(self):
		return "Section %s inherits %s, but %s wasn't found" % (self.file, self.base, self.trg)

class ClassRequired(BaseException):
	"""Section type requires a class, but one wasn't specified"""
	def __init__(self, sectname, type):
		self.name, type = sectname, type
	def __str__(self):
		return "Section %s doesn't define a class setting, but type '%s' requires it" % (self.name, self.type)

class UnknownTypeRequired(BaseException):
	"""Section was requested it be instantiated, but lacked a known type (type required for everything but conf grouppings)"""
	def __init__(self, sectname):
		self.name = sectname
	def __str__(self):
		return "Section %s cannot be instantiated, since it lacks a type setting" % self.name

class InstantiationError(BaseException):
	"""Exception occured during instantiation.  Actual exception is stored in instance.exc"""
	def __init__(self, callablename, pargs, kwargs, exception):
		self.callable, self.pargs, self.kwargs, self.exc = callablename, pargs, kwargs, exception
	def __str__(self):
		return "Caught exception '%s' instantiating %s" % (str(self.exc), self.callable)

class NoObjectReturned(BaseException):
	"""instantiating a callable, but either None or nothing was returned"""
	def __init__(self, callable):
		self.callable = callable
	def __str__(self):
		return "No object was returned from callable '%s'" % self.callable

class QuoteInterpretationError(BaseException):
	"""Quoting of a var was screwed up."""
	def __init__(self, s, v=None):
		self.str, self.var = s, v
	def __str__(self):
		return "Parsing of var '%s' \n%s\n failed" % (str(self.var), s)

class RequiredSetting(BaseException):
	"""A setting is required for this type, but not set in the config"""
	def __init__(self, type, section, setting):
		self.type, self.section, self.setting = type, section, setting
	def __str__(self):
		return "Type %s requires '%s' to be defined, but no setting found in '%s'" % (self.type, self.setting, self.section)

class SectionNotFound(BaseException):
	"""A specified section label was not found"""
	def __init__(self, section, var, requested):
		self.section, self.var, self.requested = section, var, requested
	def __str__(self):
		return "Section %s references section '%s' in setting '%s', but it doesn't (yet?) exist" % \
			(self.section, self.requested, self.var)

class BrokenSectionDefinition(BaseException):
	"""The conf that defines sections is invalid in some respect"""
	def __init__(self, section, errormsg):
		self.section, self.errmsg = section, errormsg
	def __str__(self):
		return "Section '%s' definition: error %s" % (self.section, self.errmsg)

