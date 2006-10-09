# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""
configuration subsystem primitives

all callables can/may throw a
L{configuration exception<pkgcore.config.errors.ConfigurationError>}
"""


from pkgcore.config import errors, configurable, ConfigHint
from pkgcore.util import currying
from pkgcore.util.demandload import demandload
demandload(globals(), "inspect pkgcore.util:modules")

type_names = (
    "list", "str", "bool", "section_ref", "section_refs")


class ConfigType(object):

    """A configurable type.

    @ivar name: string specifying the protocol the instantiated object
        conforms to.
    @ivar callable: callable used to instantiate this type.
    @ivar types: dict mapping key names to type strings.
    @ivar positional: container holding positional arguments.
    @ivar incrementals: container holding incrementals.
    @ivar required: container holding required arguments.
    @ivar allow_unknowns: controls whether unknown settings should error.
    """

    def __init__(self, func_obj):
        """Create from a callable (function, member function, class).

        It uses the defaults to determine type:
         - True or False mean it's a boolean
         - a tuple means it's a list (of strings)
         - a str means it's a string
         - some other object means it's a section_ref

        If an argument has no default, it is assumed to be a string-
        exception to this is if the callable has a pkgcore_config_type
        attr that is a L{ConfigHint} instance, in which case those
        override.
        """
        self.name = func_obj.__name__
        self.callable = func_obj
        if inspect.isclass(func_obj):
            func = func_obj.__init__
        else:
            func = func_obj
        args, varargs, varkw, defaults = inspect.getargspec(func)
        if inspect.ismethod(func):
            # chop off 'self'
            args = args[1:]
        self.types = {}
        # getargspec is weird
        if defaults is None:
            defaults = ()
        # iterate through defaults backwards, so they match up to argnames
        for i, default in enumerate(defaults[::-1]):
            argname = args[-1 - i]
            if default is True or default is False:
                self.types[argname] = 'bool'
            elif isinstance(default, tuple):
                self.types[argname] = 'list'
            elif isinstance(default, str):
                self.types[argname] = 'str'
            else:
                self.types[argname] = 'section_ref'
        # just [:-len(defaults)] doesn't work if there are no defaults
        self.positional = args[:len(args)-len(defaults)]
        # no defaults to determine the type from -> default to str.
        for arg in self.positional:
            self.types[arg] = 'str'
        self.required = list(self.positional)
        self.incrementals = []
        self.allow_unknowns = False

        # Process ConfigHint (if any)
        hint_overrides = getattr(func_obj, "pkgcore_config_type", None)
        if hint_overrides is not None:
            if not isinstance(hint_overrides, ConfigHint):
                raise TypeError('pkgcore_config_type should be a ConfigHint')
            self.types.update(hint_overrides.types)
            if hint_overrides.required:
                self.required = list(hint_overrides.required)
            if hint_overrides.positional:
                self.positional = list(hint_overrides.positional)
            if hint_overrides.typename:
                self.name = hint_overrides.typename
            if hint_overrides.incrementals:
                self.incrementals = hint_overrides.incrementals
            self.allow_unknowns = hint_overrides.allow_unknowns
        elif varargs is not None or varkw is not None:
            raise TypeError(
                'func %s accepts *args or **kwargs, and no ConfigHint is '
                'provided' % (self.callable,))

        for var in ('class', 'inherit', 'default'):
            if var in self.types:
                raise errors.TypeDefinitionError(
                    '%s: you cannot change the type of %r' % (
                        self.callable, var))

        for var in self.positional:
            if var not in self.required:
                raise errors.TypeDefinitionError(
                    '%s: %r is in positionals but not in required' %
                    (self.callable, var))


class LazySectionRef(object):

    """Abstract base class for lazy-loaded section references."""

    def __init__(self, central, typename):
        self.central = central
        split = typename.split(':', 1)
        if len(split) == 1:
            self.typename = None
        else:
            self.typename = split[1]
        self.cached_config = None

    def _collapse(self):
        """Override this in a subclass."""
        raise NotImplementedError(self)

    def collapse(self):
        """@returns: a L{CollapsedConfig<pkgcore.config.CollapsedConfig>}."""
        if self.cached_config is None:
            config = self.cached_config = self._collapse()
            if self.typename is not None and config.type.name != self.typename:
                raise errors.ConfigurationError(
                    'reference should be of type %r, got %r' % (
                        self.typename, config.type.name))
        return self.cached_config

    def instantiate(self):
        """Convenience method returning the instantiated section."""
        return self.collapse().instantiate()


class LazyNamedSectionRef(LazySectionRef):

    def __init__(self, central, typename, name):
        LazySectionRef.__init__(self, central, typename)
        self.name = name

    def _collapse(self):
        return self.central.collapse_named_section(self.name)


class LazyUnnamedSectionRef(LazySectionRef):

    def __init__(self, central, typename, section):
        LazySectionRef.__init__(self, central, typename)
        self.section = section

    def _collapse(self):
        return self.central.collapse_section(self.section)


class ConfigSection(object):

    """
    Single Config section, returning typed values from a key.

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


class DictConfigSection(ConfigSection):

    """Turns a dict and a conversion function into a ConfigSection."""

    def __init__(self, conversion_func, source_dict):
        """Initialize.

        @type  conversion_func: callable.
        @param conversion_func: called with a ConfigManager, a value from
            the dict and a type name.
        @type  source_dict: dict with string keys and arbitrary values.
        """
        ConfigSection.__init__(self)
        self.func = conversion_func
        self.dict = source_dict

    def __contains__(self, name):
        return name in self.dict

    def keys(self):
        return self.dict.keys()

    def get_value(self, central, name, arg_type):
        try:
            return self.func(central, self.dict[name], arg_type)
        except errors.ConfigurationError, e:
            e.stack.append('Converting argument %r to %s' % (name, arg_type))
            raise


def convert_string(central, value, arg_type):
    """Conversion func for a string-based DictConfigSection."""
    assert isinstance(value, basestring), value
    if arg_type == 'callable':
        try:
            func = modules.load_attribute(value)
        except modules.FailedImport:
            raise errors.ConfigurationError('cannot import %r' % (value,))
        if not callable(func):
            raise errors.ConfigurationError('%r is not callable' % (value,))
        return func
    elif arg_type == 'section_refs' or arg_type.startswith('refs:'):
        try:
            return list(LazyNamedSectionRef(central, arg_type, ref)
                        for ref in list_parser(value))
        except errors.QuoteInterpretationError, e:
            # TODO improve this (maybe)
            raise errors.ConfigurationError(str(e))
    elif arg_type == 'section_ref' or arg_type.startswith('ref:'):
        return LazyNamedSectionRef(central, arg_type, str_parser(value))
    try:
        func = {
            'list': list_parser,
            'str': str_parser,
            'bool': bool_parser,
            }[arg_type]
    except KeyError:
        raise errors.ConfigurationError('Unknown type %r' % (arg_type,))
    try:
        return func(value)
    except errors.QuoteInterpretationError, e:
        # TODO improve this (maybe)
        raise errors.ConfigurationError(str(e))

def convert_asis(central, value, arg_type):
    """"Conversion" func assuming the types are already correct."""
    if arg_type == 'callable':
        if not callable(value):
            raise errors.ConfigurationError('%r is not callable' % (value,))
        return value
    elif arg_type == 'section_ref' or arg_type.startswith('ref:'):
        if not isinstance(value, ConfigSection):
            raise errors.ConfigurationError('%r is not a config section' %
                                            (value,))
        return LazyUnnamedSectionRef(central, arg_type, value)
    elif arg_type == 'section_refs' or arg_type.startswith('refs:'):
        l = []
        for section in value:
            if not isinstance(section, ConfigSection):
                raise errors.ConfigurationError('%r is not a config section' %
                                                (value,))
            l.append(LazyUnnamedSectionRef(central, arg_type, section))
        return l
    elif not isinstance(value, {'list': (list, tuple),
                                'str': str,
                                'bool': bool}[arg_type]):
        raise errors.ConfigurationError(
            '%r does not have type %r' % (value, arg_type))
    return value

def convert_hybrid(central, value, arg_type):
    """Automagically switch between L{convert_string} and L{convert_asis}.

    L{convert_asis} is used for arg_type str and if value is not a basestring.
    L{convert_string} is used for the rest.

    Be careful about handing in escaped strings: they are not
    unescaped (for arg_type str).
    """
    if arg_type != 'str' and isinstance(value, basestring):
        return convert_string(central, value, arg_type)
    return convert_asis(central, value, arg_type)

# "Invalid name" (pylint thinks these are module-level constants)
# pylint: disable-msg=C0103
HardCodedConfigSection = currying.pre_curry(DictConfigSection, convert_asis)
ConfigSectionFromStringDict = currying.pre_curry(DictConfigSection,
                                                 convert_string)
AutoConfigSection = currying.pre_curry(DictConfigSection, convert_hybrid)


def section_alias(target, typename=None):
    """Build a ConfigSection that instantiates a named reference.

    Because of central's caching our instantiated value will be
    identical to our target's.
    """
    if typename is None:
        target_type = 'section_ref'
    else:
        target_type = 'ref:' + typename
    @configurable({'target': target_type}, typename=typename)
    def alias(target):
        return target
    return AutoConfigSection({'class': alias, 'target': target})


def list_parser(string):
    """split on whitespace honoring quoting for new tokens"""
    l = []
    i = 0
    e = len(string)
    # check for stringness because we return something interesting if
    # feeded a sequence of strings
    if not isinstance(string, basestring):
        raise TypeError('expected a string, got %r' % (string,))
    while i < e:
        if not string[i].isspace():
            if string[i] in ("'", '"'):
                q = i
                i += 1
                res = []
                while i < e and string[i] != string[q]:
                    if string[i] == '\\':
                        i += 1
                    res.append(string[i])
                    i += 1
                if i >= e:
                    raise errors.QuoteInterpretationError(string)
                l.append(''.join(res))
            else:
                res = []
                while i < e and not (string[i].isspace() or
                                     string[i] in ("'", '"')):
                    if string[i] == '\\':
                        i += 1
                    res.append(string[i])
                    i += 1
                if i < e and string[i] in ("'", '"'):
                    raise errors.QuoteInterpretationError(string)
                l.append(''.join(res))
        i += 1
    return l

def str_parser(string):
    """yank leading/trailing whitespace and quotation, along with newlines"""
    if not isinstance(string, basestring):
        raise TypeError('expected a string, got %r' % (string,))
    s = string.strip()
    if len(s) > 1 and s[0] in '"\'' and s[0] == s[-1]:
        s = s[1:-1]
    return s.replace('\n', ' ').replace('\t', ' ')

def bool_parser(string):
    """convert a string to a boolean"""
    s = str_parser(string).lower()
    if s in ("no", "false", "0"):
        return False
    if s in ("yes", "true", "1"):
        return True
    raise errors.ConfigurationError('%r is not a boolean' % s)


@configurable({'path': 'str', 'parser': 'callable'}, typename='configsection')
def parse_config_file(path, parser):
    try:
        f = open(path, 'r')
    except (IOError, OSError), e:
        raise errors.InstantiationError(e.strerror)
    try:
        return parser(f)
    finally:
        f.close()
