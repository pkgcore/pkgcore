# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$

__all__ = ["trigger", "SimpleTrigger", "merge_trigger", "unmerge_trigger", "ldconfig_trigger"]

import os
basename = os.path.basename
from pkgcore.fs import ops
from pkgcore.spawn import spawn
from pkgcore.merge import errors

class trigger(object):

	def __init__(self, cset_name, ftrigger, register_func=None):
		if not isinstance(cset_name, basestring):
			for x in cset_name:
				if not isinstance(x, basestring):
					raise TypeError("cset_name must be either a list, or a list of strings: %s" % x)
		else:
			cset_name = [cset_name]
		self.required_csets = cset_name
		if not callable(ftrigger):
			raise TypeError("ftrigger must be a callable")
		self.trigger = ftrigger
		if register_func is not None:
			if not callable(register_func):
				raise TypeError("register_func must be a callable")
		self.register_func = register_func
	
	# this should probably be implemented as an associated int that can be used to
	# sort the triggers
	def register(self, hook_name, existing_triggers):
		if self.register_func is not None:
			self.register_func(self, hook_name, existing_triggers)
		else:
			existing_triggers.append(self)
	
	def __call__(self, engine, csets):
		self.trigger(engine, csets)


class SimpleTrigger(trigger):

	def __init__(self, cset_name, ftrigger, register_func=None):
		if not isinstance(cset_name, basestring):
			raise TypeError("cset_name must be a string")
		trigger.__init__(self, [cset_name], ftrigger, register_func=register_func)
	
	def __call__(self, engine, csets):
		self.trigger(engine, csets[self.required_csets[0]])
		

def run_ldconfig(engine, cset, ld_so_conf_file="etc/ld.so.conf"):
	# this sucks. not very fine grained, plus it can false positive on binaries
	# libtool fex, which isn't a lib
	fireit = False
	for x in cset.iterfiles():
		s=x.location
		if s[-3:] == ".so":
			pass
		elif basename(s[:3]).lower() != "lib":
			pass
		else:
			continue
		fireit = True
		break

	if fireit:
		if engine.offset is None:
			offset = '/'
		else:
			offset = engine.offset
		basedir = os.path.join(offset, os.path.dirname(ld_so_conf_file))
		if not os.path.exists(basedir):
			os.mkdir(os.path.join(offset, basedir))
		f = os.path.join(offset, ld_so_conf_file)
		if not os.path.exists(f):
			open(f, "w")
		ret = spawn(["/sbin/ldconfig", "-r", offset], fd_pipes={1:1,2:2})
		if ret != 0:
			raise errors.TriggerWarning("ldconfig returned %i from execution" % ret)


def merge_trigger():
	return SimpleTrigger("install", 
		lambda engine,cset:ops.merge_contents(cset, offset=engine.offset))

def unmerge_trigger():
	return SimpleTrigger("uninstall", lambda e,c: ops.unmerge_contents(c))

def ldconfig_trigger():
	return SimpleTrigger("modifying", run_ldconfig)

