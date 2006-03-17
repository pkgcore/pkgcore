# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# pre merge triggers
# post merge triggers
# ordering?

import os, errno
from itertools import ifilterfalse

from pkgcore.fs.contents import contentsSet
from pkgcore.fs.ops import merge_contents
from pkgcore.fs import gen_obj as gen_fs_obj
from pkgcore.util.mappings import LazyValDict, ImmutableDict, ProtectedDict, StackedDict
from pkgcore.util import currying
from pkgcore import spawn


def scan_livefs(cset):
	for x in cset:
		try:
			yield gen_fs_obj(x.location)
		except OSError, oe:
			if oe.errno != errno.ENOENT:
				raise
			del oe


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

def merge_trigger():
	return trigger("install", lambda s,c: merge_contents(csets["install"]))

def unmerge_contents(cset):
	for x in ifilterfalse(lambda x: isinstance(x, fsDir), self.pkg.contents):
		try:
			os.unlink(x.location)
		except OSError, e:
			if e.errno != errno.ENOENT:
				raise
	for x in cset.iterdirs():
		try:
			os.rmdir(x.location)
		except OSError, e:
			if e.errno != errno.ENOTEMPTY:
				raise
			
def unmerge_trigger():
	return trigger("uninstall", lambda s,c: merge_contents(csets["uninstall"]))


def run_ldconfig(engine, csets, cset_name):
	# this sucks. not very fine grained.
	fireit = False
	for x in cset[cset_name].iterfiles():
		if x[-3:] == ".so":
			fireit = True
			break
	if fireit:
		print "would've fired ldconfig"
		return
		if engine.offset is None:
			offset = '/'
		else:
			offset = engine.offset
		ret = spawn(args = ["/sbin/ldconfig", "-r", offset], fd_pipes={1:1,2:2})
		if ret != 0:
			raise TriggerWarning("ldconfig returned %i from execution" % ret)

def ldconfig_trigger():
	# this should be just replacement once I get answers from solar/spanky about
	# symlink issues and updating cache but updating just one dir
	return trigger("modifying", currying.post_curry(run_ldconfig, "modifying"))

def alias_cset(alias, engine, csets):
	return csets[alias]

class MergeEngine(object):
	REPLACING_MODE = 0
	INSTALL_MODE = 1
	UNINSTALL_MODE = 2

#	replace_hooks = dict((x, []) for x in ["sanity_check", "pre_modify", "modify", "post_modify", "final"])

	merge_hooks = dict((x, []) for x in ["sanity_check", "pre_modify", "modify", "post_modify", "final"])
	unmerge_hooks = dict((x, []) for x in merge_hooks.keys())
	merge_hooks["modify"].append(merge_trigger)
	unmerge_hooks["modify"].append(unmerge_trigger)
	merge_hooks["post_modify"].append(ldconfig_trigger)
	unmerge_hooks["post_modify"].append(ldconfig_trigger)

	merge_csets = {"livefs_intersect":"get_livefs_intersect_cset"}
	unmerge_csets = dict(merge_csets)
	merge_csets.update({}.fromkeys(["install", "replace", "modifying"], currying.pre_curry(alias_cset, "new_cset")))
	unmerge_csets.update({}.fromkeys(["uninstall", "modifying"], currying.pre_curry(alias_cset, "old_cset")))
	merge_csets_preserve = ["new_cset"]
	unmerge_csets_preserve = ["old_cset"]

	def __init__(self, mode, hooks, csets, preserves, offset=None):
		self.mode = mode
		self.hooks = ImmutableDict((x, []) for x in hooks)
		
		self.preserve_csets = []
		self.cset_sources = {}
		# instantiate these seperately so their values are preserved
		self.preserved_csets = LazyValDict(self.preserve_csets, self._get_cset_source)
		for k,v in csets.iteritems():
			if isinstance(v, basestring):
				v = getattr(self, v, v)
			if not callable(v):
				raise TypeError("cset values must be either the string name of existing methods, or callables")
			if k in preserves:
				self.add_preserved_cset(k, v)
			else:
				self.add_cset(k, v)

		self.offset = offset
		for k, v in hooks.iteritems():
			print "adding",k
			self.add_triggers(k, *v)

		self.regenerate_csets()

	@classmethod
	def merge(cls, pkg, offset=None):
		hooks = dict((k, [y() for y in v]) for (k,v) in cls.merge_hooks.iteritems())
		csets = dict(cls.merge_csets)
		if "new_cset" not in csets:
			csets["new_cset"] = currying.post_curry(cls.get_pkg_contents, pkg)
		print csets.keys()
		print hooks
		o = cls(cls.INSTALL_MODE, hooks, csets, cls.merge_csets_preserve, offset=offset)

		if offset:
			# wrap the results of new_cset to pass through an offset generator
			o.cset_sources["new_cset"] = currying.post_curry(o.generate_offset_cset, o.cset_sources["new_cset"])
			
		o.new = pkg
		return o

	@classmethod
	def unmerge(cls, pkg, offset=None):
		hooks = dict((k, [y() for y in v]) for (k,v) in cls.unmerge_hooks.iteritems())
		csets = dict(cls.unmerge_csets)
		if "old_cset" not in csets:
			csets["old_cset"] = currying.post_curry(cls.get_pkg_contents, pkg)
		o = cls(cls.UNINSTALL_MODE, hooks, csets, cls.unmerge_csets_preserve, offset=offset)

		if offset:
			# wrap the results of new_cset to pass through an offset generator
			o.cset_sources["old_cset"] = currying.post_curry(o.generate_offset_cset, o.cset_sources["old_cset"])
			
		o.old = pkg
		return o


	def regenerate_csets(self):
		self.csets = StackedDict(self.preserved_csets, 
			LazyValDict(self.cset_sources, self._get_cset_source))

	def _get_cset_source(self, key):
		return self.cset_sources[key](self, self.csets)

	def add_preserved_cset(self, cset_name, func):
		self.add_cset(cset_name, func)
		self.preserve_csets.append(cset_name)
	
	def add_cset(self, cset_name, func):
		if not callable(func):
			raise TypeError("func must be a callable")
		if not isinstance(cset_name, basestring):
			raise TypeError("cset_name must be a string")
		self.cset_sources[cset_name] = func
	

	def add_triggers(self, hook_name, *triggers):
		if hook_name not in self.hooks:
			raise KeyError("%s isn't a known hook" % hook_name)

		for x in triggers:
			for rcs in x.required_csets:
				if rcs not in self.cset_sources:
					if isinstance(rcs, basestring):
						raise TriggerUnknownCset(rcs)
#					elif isinstance(rcs, (tuple, list)):
#						updates.update([rcs])
#					elif not callable(rcs):
#						raise TriggerUnknownCset(rcs)

		for x in triggers:
			x.register(hook_name, self.hooks[hook_name])

	@staticmethod
	def generate_offset_cset(engine, csets, cset_generator):
		return contentsSet(x.change_location(os.path.join(engine.offset, 
			x.location.lstrip(os.path.sep))) for x in cset_generator(engine, csets))

	@staticmethod
	def get_pkg_contents(engine, csets, pkg):
		"""generate the cset of what files shall be merged to the livefs"""
		return pkg.contents

	@staticmethod
	def get_remove_cset(engine, csets):
		"""generate the cset of what files shall be removed from the livefs"""
		return csets["old_cset"].difference(csets["new_cset"])

	@staticmethod
	def get_replace_cset(engine, csets):
		"""generates the cset of what will be replaced going from old -> new pkg"""
		return csets["new_cset"].intersection(csets["old_cset"])

	@staticmethod
	def get_livefs_intersect_cset(engine, csets, default_cset="modifying"):
		"""generates the livefs intersection against a cset"""
		return contentsSet(scan_livefs(csets[default_cset]))


class ModificationError(Exception):

	"""Base Exception class for modification errors/warnings"""

	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		return "%s: %s" % (self.__class__, self.msg)

	
class BlockModification(ModificationError):
	"""Merging cannot proceed"""

class TriggerUnknownCset(ModificationError):
	"""Trigger's required content set isn't known"""

class NonFatalModification(Exception):
	pass
	
class TriggerWarning(NonFatalModification):
	pass

