#!/usr/bin/python -O
# Copyright 1999-2003 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

# this is the core portageq functionality, stuck in a module so ebuild_daemon can use it.
# bin/portageq doesn't currently use this, but should for the sake of reduction of code
# duplication.

import portage,types,string


#-----------------------------------------------------------------------------
#
# To add functionality to this tool, add a function below.
#
# The format for functions is:
#
#   def function(argv):
#       """<list of options for this function>
#       <description of the function>
#       """
#       <code>
#
# "argv" is an array of the command line parameters provided after the command.
#
# Make sure you document the function in the right format.  The documentation
# is used to display help on the function.
#
# You do not need to add the function to any lists, this tool is introspective,
# and will automaticly add a command by the same name as the function!
#


def has_version(argv):
	"""<root> <category/package>
	Return code 0 if it's available, 1 otherwise.
	"""
	if (len(argv) < 2):
		print "ERROR: insufficient parameters!"
		raise Exception
	try:
		mylist=portage.db[argv[0]]["vartree"].dbapi.match(argv[1])
		if mylist:
			return 0, ""
		else:
			return 1, ""
	except KeyError:
		return 1, ""


def best_version(argv):
	"""<root> <category/package>
	Returns category/package-version (without .ebuild).
	"""
	if (len(argv) < 2):
		print "ERROR: insufficient parameters!"
		raise Exception
	try:
		mylist=portage.db[argv[0]]["vartree"].dbapi.match(argv[1])
		return 0, portage.best(mylist)
	except KeyError:
		return 1, ""


def mass_best_version(argv):
	"""<root> [<category/package>]+
	Returns category/package-version (without .ebuild).
	"""
	if (len(argv) < 2):
		print "ERROR: insufficient parameters!"
		raise Exception
	try:
		s=''
		for pack in argv[1:]:
			mylist=portage.db[argv[0]]["vartree"].dbapi.match(pack)
			s += "%s:%s\n" % (pack, portage.best(mylist))
		return 0, s
	except KeyError:
		return 1, ""


def best_visible(argv):
	"""<root> [<category/package>]+
	Returns category/package-version (without .ebuild).
	"""
	if (len(argv) < 2):
		raise Exception("insufficient parameters")
	try:
		mylist=portage.db[argv[0]]["porttree"].dbapi.match(argv[1])
		return 0, portage.best(mylist)
	except KeyError:
		return 1, ""


def mass_best_visible(argv):
	"""<root> [<category/package>]+
	Returns category/package-version (without .ebuild).
	"""
	if (len(argv) < 2):
		print "ERROR: insufficient parameters!"
		raise Exception
	try:
		s=''
		for pack in argv[1:]:
			mylist=portage.db[argv[0]]["porttree"].dbapi.match(pack)
			s += "%s:%s\n" % (pack, portage.best(mylist))
		return 0,s
	except KeyError:
		return 1, ''


def all_best_visible(argv):
	"""<root>
	Returns all best_visible packages (without .ebuild).
	"""
	if (len(argv) < 1):
		print "ERROR: insufficient parameters!"
		raise Exception("ERROR: insufficient parameters!")
	
	#print portage.db[argv[0]]["porttree"].dbapi.cp_all()
	s=''
	for pkg in portage.db[argv[0]]["porttree"].dbapi.cp_all():
		mybest=portage.best(portage.db[argv[0]]["porttree"].dbapi.match(pkg))
		if mybest:
			s += mybest +"\n"
	return 0,s

def match(argv):
	"""<root> <category/package>
	Returns \n seperated list of category/package-version
	"""
	if (len(argv) < 2):
		print "ERROR: insufficient parameters!"
		raise Exception
	try:
		return 0, string.join(portage.db[argv[0]]["vartree"].dbapi.match(argv[1]),"\n")
	except KeyError:
		return 1,''


def vdb_path(argv):
	"""
	Returns the path used for the var(installed) package database for the
	set environment/configuration options.
	"""
	return 0, portage.root+portage.VDB_PATH+"\n"

def gentoo_mirrors(argv):
	"""
	Returns the mirrors set to use in the portage configuration.
	"""
	return 0,portage.settings["GENTOO_MIRRORS"]+"\n"


def portdir(argv):
	"""
	Returns the PORTDIR path as defined in the portage configuration.
	"""
	return 0, portage.settings["PORTDIR"]+"\n"


def config_protect(argv):
	"""
	Returns the CONFIG_PROTECT paths as defined in the portage configuration.
	"""
	return 0, portage.settings["PORTDIR"]+"\n"


def config_protect_mask(argv):
	"""
	Returns the CONFIG_PROTECT_MASK paths as defined in the portage configuration.
	"""
	return 0, portage.settings["CONFIG_PROTECT_MASK"]+"\n"


def portdir_overlay(argv):
	"""
	Returns the PORTDIR_OVERLAY path as defined in the portage configuration.
	"""
	return 0, portage.settings["PORTDIR_OVERLAY"]+"\n"


def pkgdir(argv):
	"""
	Returns the PKGDIR path as defined in the portage configuration.
	"""
	return 0, portage.settings["PKGDIR"]+"\n"


def distdir(argv):
	"""
	Returns the DISTDIR path as defined in the portage configuration.
	"""
	return 0, portage.settings["DISTDIR"]+"\n"


def envvar(argv):
	"""<variable>
	Returns a specific environment variable as exists prior to ebuild.sh.
	Similar to: emerge --verbose --info | egrep '^<variable>='
	"""
	return 0, portage.settings[argv[0]]+"\n"


