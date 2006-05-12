# Copyright: 2005-2006 Marien Zwart <marienz@gentoo.org>
# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""Collapse multiple config- and type-datasources and instantiate from them"""

from pkgcore.config import errors
from pkgcore.util.mappings import LazyValDict
from pkgcore.util.currying import pre_curry


class ConfigManager(object):

	def __init__(self, configTypes, configs):
		"""Initialize.

		configTypes is a sequence of mappings of strings to ConfigType.
		configs is a sequence of mappings of strings to ConfigSections.
		"""
		# TODO autoexecs
		self.configs = list(configs)
		self.instantiated = {}
		self.types = {}
		for types in configTypes:
			for type_name, type_obj in types.iteritems():
				if type_name in self.types:
					raise errors.BaseException(
						'type %r was defined twice' % type_name)
				self.types[type_name] = type_obj
				setattr(self, type_name, LazyValDict(
						pre_curry(self.sections, type_name),
						self.instantiate_section))
		
	def sections(self, type_name=None):
		"""With no arguments, return a list of all section names.

		With an argument, restrict to sections of that type.
		"""
		res = []
		for config in self.configs:
			if type_name is None:
				res.extend(config.keys())
			else:
				for name, conf in config.iteritems():
					if ('type' in conf and
						conf.get_value(self, 'type', 'str') == type_name):
						res.append(name)
		return res

	def get_section_config(self, section):
		for config in self.configs:
			if section in config:
				return config[section]
		raise KeyError(section)

	def collapse_config(self, section, conf=None):
		"""collapse a section's config to a dict for instantiating it."""
		if conf is None:
			conf = self.get_section_config(section)
		if 'type' not in conf:
			raise errors.ConfigurationError('%s: type not set' % section)
		type_name = conf.get_value(self, 'type', 'str')
		type_obj = self.types[type_name]

		slist = [(section, conf)]

		# first map out inherits.
		for current_section, current_conf in slist:
			if 'inherit' in current_conf:
				for inherit in current_conf.get_value(
					self, 'inherit', 'list'):
					try:
						inherited_conf = self.get_section_config(inherit)
					except KeyError:
						raise errors.ConfigurationError(
							'%s: inherit target %r cannot be found' %
							(current_section, inherit))
					else:
						slist.append((inherit, inherited_conf))
		# collapse, honoring incrementals.
		
		# remember that inherit's are l->r.	 So the slist above works
		# with incrementals, and default overrides (doesn't look it,
		# but it does. tree isn't needed, list suffices)

		conf = {}
		while slist:
			inherit_name, inherit_conf = slist.pop(-1)
			additions = {}
			for x in inherit_conf.keys():
				try:
					typename = type_obj.types[x]
				except KeyError:
					raise errors.ConfigurationError(
						'%r: type of %r inherited from %r unknown' % (
							section, x, inherit_name))
				additions[x] = inherit_conf.get_value(self, x, typename)
			for x in type_obj.incrementals:
				if x in additions and x in conf:
					additions[x] = conf[x] + additions[x]

			conf.update(additions)

		conf.pop('inherit', None)

		# grab any required defaults from the type
		for default in type_obj.defaults.keys():
			if default not in conf:
				conf[default] = type_obj.defaults.get_value(
					self, default, type_obj.types[default])

		for var in type_obj.required:
			if var not in conf:
				raise errors.ConfigurationError(
					'type %r needs a setting for %r in section %r' %
					(type_name, var, section))
		
		return conf

	def instantiate_section(self, section, conf=None, allow_reuse=True):
		"""make a section config into an actual object.
		
		if conf is specified, allow_reuse is forced to false.
		if conf isn't specified, it's pulled via get_section_config.
		allow_reuse controls whether existing instantiations of that section
		can be reused or not.
		"""
		if allow_reuse:
			if section in self.instantiated:
				return self.instantiated[section]

		# collapse_config will call get_section_config if conf is None
		conf = self.collapse_config(section, conf)

		type_name = conf['type']
		del conf['type']
		
		if 'class' not in conf:
			raise errors.ConfigurationError(
				'%s: no class specified' % section)
		callable_obj = conf['class']
		del conf['class']

		pargs = []
		for var in self.types[type_name].positional:
			pargs.append(conf[var])
			del conf[var]
		try:
			obj=callable_obj(*pargs, **conf)
		except (RuntimeError, SystemExit, errors.InstantiationError):
			raise
		except Exception, e:
			if not __debug__:
				raise errors.InstantiationError(callable_obj, pargs, conf, e)
			raise
		if obj is None:
			raise errors.InstantiationError(
				callable_obj, pargs, conf,
				errors.BaseException('No object returned'))

		if allow_reuse:
			self.instantiated[section] = obj

		return obj
