# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: conditionals.py 1911 2005-08-25 03:44:21Z ferringb $

#from metadata import package as package_base
from portage.util.mappings import LimitedChangeSet, Unchangable
from portage.util.lists import unique, flatten
import copy

class base(object):
	"""base object representing a conditional node"""

	def __init__(self, node, payload, negate=False):
		self.negate, self.cond, self.restrictions = negate, node, payload

	def __str__(self):	
		if self.negate:	s="!"+self.cond
		else:					s=self.cond
		try:		s2=" ".join(self.restrictions)
		except TypeError:
			s2=str(self.restrictions)
		return "%s? ( %s )" % (s, s2)


	def __iter__(self):
		return iter(self.restrictions)

class PackageWrapper(object):
	def __init__(self, pkg_instance, configurable_attribute_name, initial_settings=[], unchangable_settings=[], attributes_to_wrap={},
		build_callback=None):

		"""pkg_instance should be an existing package instance
		configurable_attribute_name is the attribute name to fake on this instance for accessing builtup conditional changes
		use, fex, is valid for unconfigured ebuilds
		
		initial_settings is the initial settings of this beast, dict
		attributes_to_wrap should be a dict of attr_name:callable
		the callable receives the 'base' attribute (unconfigured), with the built up conditionals as a second arg
		"""
		self.__wrapped_pkg = pkg_instance
		self.__wrapped_attr = attributes_to_wrap
		if configurable_attribute_name.find(".") != -1:
			raise ValueError("can only wrap first level attributes, 'obj.dar' fex, not '%s'" % (configurable_attribute_name))
		setattr(self, configurable_attribute_name, LimitedChangeSet(initial_settings, unchangable_settings))
		self.__unchangable = unchangable_settings
		self.__configurable = getattr(self, configurable_attribute_name)
		self.__configurable_name = configurable_attribute_name
		self.__reuse_pt = 0
		self.__cached_wrapped = {}		
		self.__buildable = build_callback

	def __copy__(self):
		return self.__class__(self.__wrapped_pkg, self.__configurable_name, initial_settings=set(self.__configurable), 
			unchangable_settings=self.__unchangable, attributes_to_wrap=self.__wrapped_attr)

	def rollback(self, point=0):
		self.__configurable.rollback(point)
		# yes, nuking objs isn't necessarily required.  easier this way though.
		# XXX: optimization point
		self.__reuse_pt += 1 
	
	def commit(self):
		self.__configurable.commit()
		self.__reuse_pt = 0
		
	def changes_count(self):
		return self.__configurable.changes_count()
	
	def request_enable(self, attr, *vals):
		if attr not in self.__wrapped_attr:
			if attr == self.__configurable_name:
				entry_point = self.changes_count()
				try:
					map(self.__configurable.add, vals)
					self.__reuse_pt += 1
					return True
				except Unchangable:
					self.rollback(entry_point)
			return False
		entry_point = self.changes_count()
		a = getattr(self.__wrapped_pkg, attr)
		try:
			for x in vals:
				if x in a.node_conds:
					map(self.__configurable.add, a.node_conds[x])
				else:
					if x not in a:
						self.rollback(entry_point)
						return False
		except Unchangable:
			self.rollback(entry_point)
			return False
		self.__reuse_pt += 1
		return True

	def request_disable(self, attr, *vals):
		if attr not in self.__wrapped_attr:
			if attr == self.__configurable_name:
				entry_point = self.changes_count()
				try:
					map(self.__configurable.remove, vals)
					return True
				except Unchangable:
					self.rollback(entry_point)
			return False
		entry_point = self.changes_count()
		a = getattr(self.__wrapped_pkg, attr)
		try:
			for x in vals:
				if x in a.node_conds:
						map(self.__configurable.remove, a.node_conds[x])
				else:
					if x in a:
						self.rollback(entry_point)
						return False
		except Unchangable:
			self.rollback(entry_point)
			return False
		self.__reuse_pt += 1
		return True

	def __getattr__(self, attr):
		if attr in self.__wrapped_attr:
			if attr in self.__cached_wrapped:
				if self.__cached_wrapped[attr][0] == self.__reuse_pt:
					return self.__cached_wrapped[attr][1]
				del self.__cached_wrapped[attr]
			o = self.__wrapped_attr[attr](getattr(self.__wrapped_pkg, attr), self.__configurable)
			self.__cached_wrapped[attr] = (self.__reuse_pt, o)
			return o
		else:
			return getattr(self.__wrapped_pkg, attr)

	def __str__(self):
		return "config wrapper: %s, configurable('%s'):%s" % (self.__wrapped_pkg, self.__configurable_name, self.__configurable)

	def freeze(self):
		o = copy.copy(self)
		o.lock()
		return o

	def lock(self):
		self.commit()
		self.__configurable = list(self.__configurable)		

		
	def build(self):
		if self.__buildable:
			return self.__buildable(self)
		return None
