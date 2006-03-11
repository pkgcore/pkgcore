# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: modules.py 2327 2005-12-02 00:13:09Z marienz $

import sys

class FailedImport(ImportError):
	def __init__(self, trg, e):	self.trg, self.e = trg, e
	def __str__(self):	return "Failed importing target '%s': '%s'" % (self.trg, self.e)


def load_module(name):
	"""load a module, throwing a FailedImport if __import__ fails"""
	if name in sys.modules:
	    return sys.modules[name]
	try:
		m = __import__(name)
		nl = name.split('.')
		# __import__ returns nl[0]... so.
		nl.pop(0)
		while nl:
			m = getattr(m, nl[0])
			nl.pop(0)
		return m
	except (KeyboardInterrupt, SystemExit):
		raise
	except Exception, e:
		raise FailedImport(name, e)

def load_attribute(name):
	"""load a specific attribute, rather then a module"""
	try:
		i = name.rfind(".")
		if i == -1:
			raise FailedImport(name, "it isn't an attribute, it's a module")
		m = load_module(name[:i])
		m = getattr(m, name[i+1:])
		return m
	except (AttributeError, ImportError), e:
		raise FailedImport(name, e)

