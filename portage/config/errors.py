# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: errors.py 2272 2005-11-10 00:19:01Z ferringb $

# potentially use an intermediate base for user config errors,
# seperate base for instantiation?


"""Exceptions raised by the config code."""


class BaseException(Exception):

	def __init__(self, *args, **kwargs):
		Exception.__init__(self, *args, **kwargs)

	def __str__(self):
		return self.args[0]

		
class TypeDefinitionError(BaseException):
	
	"""Fatal error in type construction."""
	
	def __init__(self, *args, **kwargs):
		BaseException.__init__(self, *args, **kwargs)

	
class ConfigurationError(BaseException):
	
	"""Fatal error in parsing a config section."""
	
	def __init__(self, *args, **kwargs):
		BaseException.__init__(self, *args, **kwargs)


class InstantiationError(BaseException):
	"""Exception occured during instantiation.	Actual exception is stored in instance.exc"""
	def __init__(self, callablename, pargs, kwargs, exception):
		self.callable, self.pargs, self.kwargs, self.exc = callablename, pargs, kwargs, exception
	def __str__(self):
		return "Caught exception '%s' instantiating %s" % (str(self.exc), self.callable)

class QuoteInterpretationError(BaseException):
	
	"""Quoting of a var was screwed up.

	It may be useful to catch this and raise a ConfigurationError at a
	point where the filename is known.
	"""
	
	def __init__(self, string):
		self.str = string
		
	def __str__(self):
		return "Parsing of %r failed" % self.str
