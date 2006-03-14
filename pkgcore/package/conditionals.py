# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.mappings import LimitedChangeSet, Unchangable
from pkgcore.util.lists import unique, flatten
import copy

class PackageWrapper(object):
	def __init__(self, pkg_instance, configurable_attribute_name, initial_settings=None, unchangable_settings=None, 
		attributes_to_wrap=None, build_callback=None):

		"""pkg_instance should be an existing package instance
		configurable_attribute_name is the attribute name to fake on this instance for accessing builtup conditional changes
		use, fex, is valid for unconfigured ebuilds
		
		initial_settings is the initial settings of this beast, dict
		attributes_to_wrap should be a dict of attr_name:callable
		the callable receives the 'base' attribute (unconfigured), with the built up conditionals as a second arg
		"""
		
		if initial_settings is None:
			initial_settings = []
		if unchangable_settings is None:
			unchangable_settings = []
		self._wrapped_pkg = pkg_instance
		if attributes_to_wrap is None:
			attributes_to_wrap = {}
		self._wrapped_attr = attributes_to_wrap
		if configurable_attribute_name.find(".") != -1:
			raise ValueError("can only wrap first level attributes, 'obj.dar' fex, not '%s'" % (configurable_attribute_name))
		setattr(self, configurable_attribute_name, LimitedChangeSet(initial_settings, unchangable_settings))
		self._unchangable = unchangable_settings
		self._configurable = getattr(self, configurable_attribute_name)
		self._configurable_name = configurable_attribute_name
		self._reuse_pt = 0
		self._cached_wrapped = {}		
		self._buildable = build_callback

	def __copy__(self):
		return self.__class__(self._wrapped_pkg, self._configurable_name, initial_settings=set(self._configurable), 
			unchangable_settings=self._unchangable, attributes_to_wrap=self._wrapped_attr)

	def rollback(self, point=0):
		self._configurable.rollback(point)
		# yes, nuking objs isn't necessarily required.  easier this way though.
		# XXX: optimization point
		self._reuse_pt += 1 
	
	def commit(self):
		self._configurable.commit()
		self._reuse_pt = 0
		
	def changes_count(self):
		return self._configurable.changes_count()
	
	def request_enable(self, attr, *vals):
		if attr not in self._wrapped_attr:
			if attr == self._configurable_name:
				entry_point = self.changes_count()
				try:
					map(self._configurable.add, vals)
					self._reuse_pt += 1
					return True
				except Unchangable:
					self.rollback(entry_point)
			return False
		entry_point = self.changes_count()
		a = getattr(self._wrapped_pkg, attr)
		try:
			for x in vals:
				if x in a.node_conds:
					map(self._configurable.add, a.node_conds[x])
				else:
					if x not in a:
						self.rollback(entry_point)
						return False
		except Unchangable:
			self.rollback(entry_point)
			return False
		self._reuse_pt += 1
		return True

	def request_disable(self, attr, *vals):
		if attr not in self._wrapped_attr:
			if attr == self._configurable_name:
				entry_point = self.changes_count()
				try:
					map(self._configurable.remove, vals)
					return True
				except Unchangable:
					self.rollback(entry_point)
			return False
		entry_point = self.changes_count()
		a = getattr(self._wrapped_pkg, attr)
		try:
			for x in vals:
				if x in a.node_conds:
						map(self._configurable.remove, a.node_conds[x])
				else:
					if x in a:
						self.rollback(entry_point)
						return False
		except Unchangable:
			self.rollback(entry_point)
			return False
		self._reuse_pt += 1
		return True

	def __getattr__(self, attr):
		if attr in self._wrapped_attr:
			if attr in self._cached_wrapped:
				if self._cached_wrapped[attr][0] == self._reuse_pt:
					return self._cached_wrapped[attr][1]
				del self._cached_wrapped[attr]
			o = self._wrapped_attr[attr](getattr(self._wrapped_pkg, attr), self._configurable)
			self._cached_wrapped[attr] = (self._reuse_pt, o)
			return o
		else:
			return getattr(self._wrapped_pkg, attr)

	def __str__(self):
		return "config wrapper: %s, configurable('%s'):%s" % (self._wrapped_pkg, self._configurable_name, self._configurable)

	def freeze(self):
		o = copy.copy(self)
		o.lock()
		return o

	def lock(self):
		self.commit()
		self._configurable = list(self._configurable)		
		
	def build(self):
		if self._buildable:
			return self._buildable(self)
		return None

	def __cmp__(self, other):
		if isinstance(self, PackageWrapper) and isinstance(other, PackageWrapper):
			c = cmp(self._wrapped_pkg, other._wrapped_pkg)
			if c == 0:
				return cmp(self._configurable, other._configurable)
			return c
		raise TypeError

