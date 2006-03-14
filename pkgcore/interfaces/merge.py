# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# pre merge triggers
# post merge triggers
# ordering?

from pkgcore.fs.contents import contentsSet
from pkgcore.fs import gen_obj as gen_fs_obj
from pkgcore.util import currying

import os, errno
import copy

def generate_cset(cset, offset=None):
	if offset:
		return contentsSet(x.change_location(os.path.join(self.offset, 
			x.location.lstrip(os.path.sep))) for x in cset)
	return cset

def scan_livefs(self, cset):
	for x in cset:
		try:
			yield gen_fs_obj(x.location)
		except OSError, oe:
			if oe.errno != errno.ENOENT:
				raise
			del oe


class MergeEngine(object):
	REPLACING_MODE = 0
	MERGING_MODE = 1
	UNMERGING_MODE = 2
	
	_default_csets = {}
	
	def __init__(self, pkg, pkg2=None, offset=None):
		self.newpkg = newpkg
		self.oldpkg = oldpkg
		self.offset = offset
		
		self.pre_triggers = []
		self.post_triggers = []
		
		# cset_name -> [ref_count, pull_func]
		self.trigger_csets = dict(self._default_csets)
		
		# icky.  temporary hack. use properties for this
		for k, obj in (("new_cset", self.newpkg), ("old_cset", self.oldpkg)):
			cs = getattr(obj, "contents", None)
			if cs is None:
				o = contentsSet()
			elif offset:
				o = contentsSet(x.change_location(os.path.join(self.offset, 
					x.location.lstrip(os.path.sep))) for x in cs)
			else:
				o = contentsSet(cs)
			setattr(self, k, o)

	@classmethod
	def replace_op(cls, old, new, offset=None):
		
	
	def _add_triggers(self, trigger_name, *triggers):
		trigger_list = getattr(self, "trigger_name")
		updates = {}
		for x in triggers:
			if x.required_cset not in trigger_csets:
				if isinstance(x.required_cset, basestring):
					raise TriggerUnknownCset(x.required_cset)
				elif isinstance(x.required_cset, (tuple, list)):
					updates.update([x.required_cset])
				elif not callable(x.required_cset):
					raise TriggerUnknownCset(x.required_cset)

		self.trigger_csets.update(updates)
		trigger_list.extend(trigger)

	add_pre_trigger = currying.pretty_docs(currying.post_curry(_add_triggers, "pre_triggers"),
		"add a trigger(s) to run prior to merging")
	add_post_trigger = currying.pretty_docs(currying.post_curry(_add_triggers, "post_triggers"),
		"add a trigger(s) to run after merging")
		
	def get_merge_cset(self):
		return self.new_cset
	
	def get_remove_cset(self):
		return self.old_cset.difference(self.new_cset)

	def get_replace_cset(self):
		return self.new_cset.intersection(self.old_cset)

	def get_livefs_intersect_cset(self):
		return contentsSet(scan_livefs(self.new_cset))
		
	_default_csets.update({"merge":get_merge_cset, "remove":get_remove_cset, 
		"replace":get_replace_cset, "livefs_intersect":get_livefs_intersect_cset})
	
	def execute(self):
		# generate the intersection against livefs.
		existing = contentsSet(self.get_livefs_intersect_cset(self.new_cset))
		

class MergeException(Exception):

	"""Base Exception class for merge exceptions"""

	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		return "%s: %s" % (self.__class__, self.msg)

	
class BlockMerging(MergeException):
	"""Merging cannot proceed"""

class TriggerUnknownCset(MergeException):
	"""Trigger's required content set isn't known"""

