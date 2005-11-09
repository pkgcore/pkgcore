# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id: modules.py 2284 2005-11-10 00:35:50Z ferringb $

import sys, threading

class FailedImport(ImportError):
	def __init__(self, trg, e):	self.trg, self.e = trg, e
	def __str__(self):	return "Failed importing target '%s': '%s'" % (self.trg, self.e)

__import_lock = threading.Lock()

def load_module(name):
	"""load a module, throwing a FailedImport if __import__ fails"""
	__import_lock.acquire()
	try:
		if name in sys.modules:
			return sys.modules[name]
		try:
			m = __import__(name)
			nl = name.split('.')
			# __import__ returns nl[0]... so.
			nl.pop(0)
			while len(nl):
				m = getattr(m, nl[0])
				nl.pop(0)
			return m
		# * ferringb|afk hit it at some point, sure of that
		# but no idea how, so commenting out to see if things break...
		# except AttributeError, e:
		#	raise FailedImport(name, e)
		except ImportError, e:
			try:
				del sys.modules[name]
			except KeyError:
				pass
			raise FailedImport(name, e)
	finally:
		__import_lock.release()

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

