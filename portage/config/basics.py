# Copyright: 2005 Gentoo Foundation
# License: GPL2


from portage.util import modules
from portage.config import errors


type_names = ("list", "str", "bool", "section_ref", "section_refs")


class ConfigType(object):

	def __init__(
		self, typename, types,
		positional=None, incrementals=None, required=None, defaults=None):
		"""A configurable 'type'.

		typename is the name of the type, used in errors.
		types is a dict mapping key names to type strings.
		positional is a list of positional arguments.
		incrementals is a list of incrementals.
		required is a list of required arguments.
		defaults is a ConfigSection with default values.
		"""
		if positional is None:
			positional = []
		if incrementals is None:
			incrementals = []
		if required is None:
			required = []
		if defaults is None:
			defaults = HardCodedConfigSection(
				'empty defaults for %r' % typename, {})

		self.typename = typename
		self.positional = positional
		self.incrementals = incrementals
		self.required = required
		self.defaults = defaults

		for var, var_typename in (
			('class', 'callable'),
			('type', 'str'),
			('inherit', 'list'),
			):
			if var in types:
				raise errors.TypeDefinitionError(
					'%s: you cannot change the type of %r' % (typename, var))
			types[var] = var_typename
		self.types = types

		for var in self.positional:
			if var not in self.required:
				raise errors.TypeDefinitionError(
					'%s: %r is in positionals but not in required' %
					(typename, var))


class ConfigSection(object):

	"""Single Config section, returning typed values from a key.

	Not much of an object this, if we were using zope.interface it'd
	be an Interface.
	"""

	def __contains__(self, name):
		"""Check if a key is in this section."""
		raise NotImplementedError

	def keys(self):
		"""Return a list of keys."""
		raise NotImplementedError
	
	def get_value(self, central, name, arg_type):
		"""Return a setting, converted to the requested type."""
		raise NotImplementedError


class ConfigSectionFromStringDict(ConfigSection):

	"""Useful for string-based config implementations."""

	def __init__(self, name, source_dict):
		self.name = name
		self.dict = source_dict

	def __contains__(self, name):
		return name in self.dict

	def keys(self):
		return self.dict.keys()
		
	def get_value(self, central, name, arg_type):
		value = self.dict[name]
		if arg_type == 'callable':
			try:
				func = modules.load_attribute(value)
			except modules.FailedImport:
				raise errors.ConfigurationError(
					'%s: cannot import %r' % (self.name, value))
			if not callable(func):
				raise errors.ConfigurationError(
					'%s: %r is not callable' % (self.name, value))
			return func
		elif arg_type == 'section_refs':
			result = []
			for section_name in list_parser(value):
				# TODO does this defeat central's instance caching?
				try:
					conf = central.get_section_config(section_name)
				except KeyError:
					raise errors.ConfigurationError(
						'%s: requested section %r for %r not found' %
						(self.name, section_name, name))
				else:
					result.append(central.instantiate_section(
							section_name, conf=conf))
			return result
		elif arg_type == 'section_ref':
			# TODO does this defeat central's instance caching?
			section_name = str_parser(value)
			try:
				conf = central.get_section_config(section_name)
			except KeyError:
				raise errors.ConfigurationError(
					'%s: requested section %r for %r not found' %
					(self.name, name, value))
			else:
				return central.instantiate_section(section_name, conf=conf)
		return {
			'list': list_parser,
			'str': str_parser,
			'bool': bool_parser,
			}[arg_type](value)


class HardCodedConfigSection(ConfigSection):

	"""Just wrap around a dict."""

	def __init__(self, name, source_dict):
		self.name = name
		self.dict = source_dict

	def __contains__(self, name):
		return name in self.dict

	def keys(self):
		return self.dict.keys()
		
	def get_value(self, central, name, arg_type):
		types = {
			'list': list,
			'str': str,
			'bool': bool,
			}
		value = self.dict[name]
		if arg_type == 'callable':
			if not callable(value):
				raise errors.ConfigurationError(
					'%s: %r is not callable' % (self.name, value))
		elif arg_type in ('section_ref', 'section_refs'):
			pass
		elif not isinstance(value, types[arg_type]):
			raise errors.ConfigurationError(
				'%s: %r does not have type %r' % (self.name, name, arg_type))
		return value


def list_parser(s):
	"""split on whitespace honoring quoting for new tokens"""
	l=[]
	i = 0
	e = len(s)
	# check for stringness because we return something interesting if
	# feeded a sequence of strings
	if not isinstance(s, basestring):
		raise TypeError('expected a string, got %r' % s)
	while i < e:
		if not s[i].isspace():
			if s[i] in ("'", '"'):
				q = i
				i += 1
				res = []
				while i < e and s[i] != s[q]:
					if s[i] == '\\':
						i+=1
					res.append(s[i])
					i+=1
				if i >= e:
					raise errors.QuoteInterpretationError(s)
				l.append(''.join(res))
			else:
				start = i
				res = []
				while i < e and not (s[i].isspace() or s[i] in ("'", '"')):
					if s[i] == '\\':
						i+=1
					res.append(s[i])
					i+=1
				if i < e and s[i] in ("'", '"'):
					raise errors.QuoteInterpretationError(s)
				l.append(''.join(res))
		i+=1
	return l

def str_parser(s):
	"""yank leading/trailing whitespace and quotation, along with newlines"""
	if not isinstance(s, basestring):
		raise TypeError('expected a string, got %r' % s)
	s = s.strip()
	if len(s) > 1 and s[0] in '"\'' and s[0] == s[-1]:
		s = s[1:-1]
	return s.replace('\n', ' ').replace('\t', ' ')
	
def bool_parser(s):
	s = str_parser(s).lower()
	if s in ("no", "false", "0"):
		return False
	if s in ("yes", "true", "1"):
		return True
	raise errors.ConfigurationError('%r is not a boolean' % s)
