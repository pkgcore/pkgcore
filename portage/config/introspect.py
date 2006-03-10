# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Use introspection to build ConfigTypes from callables."""

import inspect

from portage.config import basics


def configTypeFromCallable(func):
	"""Create a ConfigType from a callable (function, member function, class).

	It uses the defaults to determine type:
	- True or False mean it's a boolean
	- a tuple means it's a list (of strings)
	- a str means it's a string
	- some other object means it's a section_ref

	If an argument has no default, it is assumed to be a string.
	"""
	name = func.__name__
	if inspect.isclass(func):
		func = func.__init__
	args, varargs, varkw, defaults = inspect.getargspec(func)
	if varargs is not None or varkw is not None:
		raise TypeError('func accepts *args or **kwargs')
	if inspect.ismethod(func):
		# chop off 'self'
		args = args[1:]
	types = {}
	defaultsDict = {}
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
		defaultsDict[argname] = typename
	# no defaults to determine the type from -> default to str.
	# just [:-len(defaults)] doesn't work if there are no defaults
	for arg in args[:len(args)-len(defaults)]:
		types[arg] = 'str'
	return basics.ConfigType(
		name, types, required=args,
		defaults=basics.HardCodedConfigSection(
			'%s defaults' % name, defaultsDict))
