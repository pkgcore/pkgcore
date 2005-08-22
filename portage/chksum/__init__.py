# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Header$

import os

chksum_types = {}
__inited__ = False

def init(additional_handlers={}):
	"""init the chksum subsystem.  scan the dir, find what handlers are available, etc.
	if desired to register additional, or override existing, pass in a dict of type:func"""
	import sys, os, logging

	if not isinstance(additional_handlers, dict):
		raise TypeError("additional handlers must be a dict!")

	chksum_types.clear()
	__inited__ = False
	loc = os.path.dirname(sys.modules[__name__].__file__)
	for f in os.listdir(loc):
		if not f.endswith(".py") or f.startswith("__init__."):
			continue
		try:
			i = f.find(".")
			if i != -1:	f = f[:i]
			del i
			m = __import__(f)
		except ImportError:
			continue
		try:
			types = getattr(m, "chksum_types")
		except AttributeError:
			# no go.
			continue
		try:
			for name, chf in types:
				chksum_types[name] = chf

		except ValueError:
			logging.warn("%s.%s invalid chksum_types, ValueError Exception" % (__name__, f))
			continue

	chksum_types.update(additional_handlers)	

	__inited__ = True
