# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Use introspection to build ConfigTypes from callables."""

from pkgcore.util.demandload import demandload
demandload(globals(), "inspect pkgcore:config")

def configTypeFromCallable(func_obj):
	"""Create a ConfigType from a callable (function, member function, class).

	It uses the defaults to determine type:
	 - True or False mean it's a boolean
	 - a tuple means it's a list (of strings)
	 - a str means it's a string
	 - some other object means it's a section_ref

	If an argument has no default, it is assumed to be a string- exception to this is if
	the callable has a pkgcore_config_type attr that is a L{ConfigHint} instance, in which 
	case those override
	"""
	name = func_obj.__name__
	if inspect.isclass(func_obj):
		func = func_obj.__init__
	else:
		func = func_obj
	args, varargs, varkw, defaults = inspect.getargspec(func)
	if inspect.ismethod(func):
		# chop off 'self'
		args = args[1:]
	types = {}
	defaultsDict = {}
	fail = False
	if varargs is not None or varkw is not None:
		fail = True
	# getargspec is weird
	if defaults is None:
		defaults = ()
	# iterate through defaults backwards, so they match up to argnames
	for i, default in enumerate(defaults[::-1]):
		argname = args[-1 - i]
		if default is True or default is False:
			typename = 'bool'
		elif isinstance(default, tuple):
			typename = 'list'
		elif isinstance(default, str):
			typename = 'str'
		else:
			typename = 'section_ref'
		types[argname] = typename
		defaultsDict[argname] = default
	# no defaults to determine the type from -> default to str.
	# just [:-len(defaults)] doesn't work if there are no defaults
	for arg in args[:len(args)-len(defaults)]:
		types[arg] = 'str'

	hint_overrides = getattr(func_obj, "pkgcore_config_type", None)
	positional = list(args)
	if hint_overrides is not None:
		if isinstance(hint_overrides, ConfigHint):
			types.update(hint_overrides.types)
			if hint_overrides.required is not None:
				args = list(hint_overrides.required)
			if hint_overrides.positional:
				positional = list(hint_overrides.positional)
		elif not isinstance(hint_overrides, bool):
			raise config.errors.TypeDefinitionError(
				"instance %s attr pkgcore_config_type is "
				"neither a ConfigHint nor boolean" % func_obj)
		elif fail:
			raise TypeError(
				'func accepts *args or **kwargs, '
				'and no ConfigHint is provided')
	elif fail:
		raise TypeError(
			'func accepts *args or **kwargs, and no ConfigHint is provided')

	return config.basics.ConfigType(
		name, types, required=args,
		defaults=config.basics.HardCodedConfigSection(
			'%s defaults' % name, defaultsDict),
		positional=positional)


class ConfigHint(object):

	"""hint for introspection supplying overrides"""

	__slots__ = ("types", "positional", "required")
	
	def __init__(self, types=None, positional=None, required=None):
		if types is None:
			self.types = {}
		else:
			self.types = types
		self.positional, self.required = positional, required
