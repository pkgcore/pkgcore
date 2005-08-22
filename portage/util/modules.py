# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

class FailedImport(ImportError):
	def __init__(self, trg, e):	self.trg, self.e = trg, e
	def __str__(self):	return "Failed importing target '%s': '%s'" % (self.trg, self.e)

def load_module(name):
	"""load a module, throwing a FailedImport if __import__ fails"""
	try:
		m = __import__(name)
		nl = name.split('.')
		# __import__ returns nl[0]... so.
		nl.pop(0)
		while len(nl):
			m = getattr(m, nl[0])
			nl.pop(0)
		return m	
	except (AttributeError, ImportError), e:
		raise FailedImport(name, e)
	

def load_attribute(name):
	"""load a specific attribute, rather then a module"""
	try:
		i = name.rfind(".")
		if i == -1:
			raise ValueError("name isn't an attribute, it's a module... : %s" % name)
		m = load_module(name[:i])
		m = getattr(m, name[i+1:])
		return m
	except (AttributeError, ImportError), e:
		raise FailedImport(name, e)

