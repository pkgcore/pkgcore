# Copyright: 2009 Brian Harring <ferringb@gmail.com>
# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""
configuration subsystem primitives

all callables can/may throw a
L{configuration exception<pkgcore.config.errors.ConfigurationError>}
"""


from pkgcore.config import errors, configurable
from snakeoil import currying
from snakeoil import compatibility
from snakeoil.demandload import demandload
demandload(globals(), "snakeoil:modules")

type_names = ("list", "str", "bool", "int")


# Copied from inspect.py which copied it from compile.h.
# Also documented in http://docs.python.org/ref/types.html.
CO_VARARGS, CO_VARKEYWORDS = 4, 8


if compatibility.is_py3k:
    _code_attrname = '__code__'
else:
    _code_attrname = 'func_code'

class ConfigType(object):

    """A configurable type.

    @ivar name: string specifying the protocol the instantiated object
        conforms to.
    @ivar callable: callable used to instantiate this type.
    @ivar types: dict mapping key names to type strings.
    @ivar positional: container holding positional arguments.
    @ivar required: container holding required arguments.
    @ivar allow_unknowns: controls whether unknown settings should error.
    """

    def __init__(self, func_obj):
        """Create from a callable (function, member function, class).

        It uses the defaults to determine type:
         - True or False mean it's a boolean
         - a tuple means it's a list (of strings)
         - a str means it's a string

        Arguments with a default of a different type are ignored.

        If an argument has no default, it is assumed to be a string-
        exception to this is if the callable has a pkgcore_config_type
        attr that is a L{ConfigHint} instance, in which case those
        override.
        """
        self.name = func_obj.__name__
        self.callable = func_obj
        self.doc = getattr(func_obj, '__doc__', None)
        if not hasattr(func_obj, _code_attrname):
            # No function or method, should be a class so grab __init__.
            func_obj = func_obj.__init__
        # We do not use the inspect module because that is a heavy
        # thing to import and we can pretty easily get the data we
        # need without it. Most of the code in its getargs function
        # deals with tuples inside argument definitions, which we do
        # not support anyway.
        code = getattr(func_obj, _code_attrname)
        if code.co_argcount and code.co_varnames[0] == 'self':
            args = code.co_varnames[1:code.co_argcount]
        else:
            args = code.co_varnames[:code.co_argcount]
        varargs = bool(code.co_flags & CO_VARARGS)
        varkw = bool(code.co_flags & CO_VARKEYWORDS)
        defaults = func_obj.func_defaults
        if defaults is None:
            defaults = ()
        self.types = {}
        # iterate through defaults backwards, so they match up to argnames
        for i, default in enumerate(reversed(defaults)):
            argname = args[-1 - i]
            for typeobj, typename in [(bool, 'bool'),
                                      (tuple, 'list'),
                                      (str, 'str'),
                                      ((int, long), 'int')]:
                if isinstance(default, typeobj):
                    self.types[argname] = typename
                    break
        # just [:-len(defaults)] doesn't work if there are no defaults
        self.positional = args[:len(args)-len(defaults)]
        # no defaults to determine the type from -> default to str.
        for arg in self.positional:
            self.types[arg] = 'str'
        self.required = tuple(self.positional)
        self.allow_unknowns = False

        # Process ConfigHint (if any)
        hint_overrides = getattr(self.callable, "pkgcore_config_type", None)
        if hint_overrides is not None:
            self.types.update(hint_overrides.types)
            if hint_overrides.required:
                self.required = tuple(hint_overrides.required)
            if hint_overrides.positional:
                self.positional = tuple(hint_overrides.positional)
            if hint_overrides.typename:
                self.name = hint_overrides.typename
            if hint_overrides.doc:
                self.doc = hint_overrides.doc
            self.allow_unknowns = hint_overrides.allow_unknowns
        elif varargs or varkw:
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
        self.typename = typename.split(':', 1)[1]
        self.cached_config = None

    def _collapse(self):
        """Override this in a subclass."""
        raise NotImplementedError(self._collapse)

    def collapse(self):
        """@returns: L{pkgcore.config.central.CollapsedConfig}."""
        if self.cached_config is None:
            config = self.cached_config = self._collapse()
            if self.typename is not None and config.type.name != self.typename:
                raise errors.ConfigurationError(
                    'reference %r should be of type %r, got %r' % (
                        self.name, self.typename, config.type.name))
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
        raise NotImplementedError(self.__contains__)

    def keys(self):
        """Return a list of keys."""
        raise NotImplementedError(self.keys)

    def get_value(self, central, name, arg_type):
        """Return a setting, converted to the requested type."""
        raise NotImplementedError(self.get_value)


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


class FakeIncrementalDictConfigSection(ConfigSection):

    """Turns a dict and a conversion function into a ConfigSection."""

    def __init__(self, conversion_func, source_dict):
        """Initialize.

        A request for a section of a list type will look for
        name.prepend and name.append keys too, using those for values
        prepended/appended to the inherited values. The conversion
        func should return a single sequence for list types and in
        repr for list types.

        @type  conversion_func: callable.
        @param conversion_func: called with a ConfigManager, a value from
            the dict and a type name.
        @type  source_dict: dict with string keys and arbitrary values.
        """
        ConfigSection.__init__(self)
        self.func = conversion_func
        self.dict = source_dict

    def __contains__(self, name):
        return name in self.dict or name + '.append' in self.dict or \
            name + '.prepend' in self.dict

    def keys(self):
        keys = set()
        for key in self.dict:
            if key.endswith('.append'):
                keys.add(key[:-7])
            elif key.endswith('.prepend'):
                keys.add(key[:-8])
            else:
                keys.add(key)
        return list(keys)

    def get_value(self, central, name, arg_type):
        # Check if we need our special incremental magic.
        if arg_type in ('list', 'str', 'repr') or arg_type.startswith('refs:'):
            result = []
            # Careful: None is a valid dict value, so use something else here.
            missing = object()
            for subname in (name + '.prepend', name, name + '.append'):
                val = self.dict.get(subname, missing)
                if val is missing:
                    val = None
                else:
                    try:
                        val = self.func(central, val, arg_type)
                    except errors.ConfigurationError, e:
                        e.stack.append('Converting argument %r to %s' % (
                                subname, arg_type))
                        raise
                result.append(val)
            if result[0] is result[1] is result[2] is None:
                raise KeyError(name)
            if arg_type != 'repr':
                # Done.
                return result
            # If "kind" is of some incremental-ish kind or we have
            # .prepend or .append for this key then we need to
            # convert everything we have to the same kind and
            # return all three.
            #
            # (we do not get called for separate reprs for the
            # .prepend or .append because those are filtered from
            # .keys(). If we do not filter those from .keys()
            # central gets upset because it does not know their
            # type. Perhaps this means we should have a separate
            # .keys() used together with repr, not sure yet
            # --marienz)
            #
            # The problem here is that we may get unsuitable for
            # incremental or differing types for the three reprs
            # we run, so we need to convert to a suitable common
            # kind.
            if result[0] is None and result[2] is None:
                # Simple case: no extra data, so no need for any
                # conversions.
                kind, val = result[1]
                if kind in ('list', 'str') or kind == 'refs':
                    # Caller expects a three-tuple.
                    return kind, (None, val, None)
                else:
                    # non-incremental, just return as-is.
                    return kind, val
            # We have more than one return value. Figure out what
            # target to convert to. Choices are list, str and refs.
            kinds = set(v[0] for v in result if v is not None)
            if 'refs' in kinds or 'ref' in kinds:
                # If we have any refs we have to convert to refs.
                target_kind = 'refs'
            elif kinds == set(['str']):
                # If we have only str we can just use that.
                target_kind = 'str'
            else:
                # Convert to list. May not make any sense, but is
                # the best we can do.
                target_kind = 'list'
            converted = []
            for val in result:
                if val is None:
                    converted.append(None)
                    continue
                kind, val = val
                if kind == 'ref':
                    assert target_kind == 'refs', target_kind
                    converted.append([val])
                elif kind == 'refs':
                    assert target_kind == 'refs', target_kind
                    converted.append(val)
                elif kind == 'list':
                    assert target_kind != 'str', target_kind
                    converted.append(val)
                else:
                    # Everything else gets converted to a string first.
                    if kind == 'callable':
                        val = '%s.%s' % (val.__module__, val.__name__)
                    elif kind in ('bool', 'int', 'str'):
                        val = str(val)
                    else:
                        raise errors.ConfigurationError(
                            'unsupported type %r' % (kind,))
                    # Then convert the str to list if needed.
                    if target_kind == 'str':
                        converted.append(val)
                    else:
                        converted.append([val])
            return target_kind, converted
        # Not incremental.
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
    elif arg_type.startswith('refs:'):
        return list(LazyNamedSectionRef(central, arg_type, ref)
                    for ref in list_parser(value))
    elif arg_type.startswith('ref:'):
        return LazyNamedSectionRef(central, arg_type, str_parser(value))
    elif arg_type == 'repr':
        return 'str', value
    try:
        func = {
            'list': list_parser,
            'str': str_parser,
            'bool': bool_parser,
            'int': int_parser,
            }[arg_type]
    except KeyError:
        raise errors.ConfigurationError('Unknown type %r' % (arg_type,))
    return func(value)

def convert_asis(central, value, arg_type):
    """"Conversion" func assuming the types are already correct."""
    if arg_type == 'callable':
        if not callable(value):
            raise errors.ConfigurationError('%r is not callable' % (value,))
        return value
    elif arg_type.startswith('ref:'):
        if not isinstance(value, ConfigSection):
            raise errors.ConfigurationError('%r is not a config section' %
                                            (value,))
        return LazyUnnamedSectionRef(central, arg_type, value)
    elif arg_type.startswith('refs:'):
        l = []
        for section in value:
            if not isinstance(section, ConfigSection):
                raise errors.ConfigurationError('%r is not a config section' %
                                                (value,))
            l.append(LazyUnnamedSectionRef(central, arg_type, section))
        return l
    elif arg_type == 'repr':
        if callable(value):
            return 'callable', value
        if isinstance(value, ConfigSection):
            return 'ref', value
        if isinstance(value, str):
            return 'str', value
        if isinstance(value, bool):
            return 'bool', value
        if isinstance(value, (list, tuple)):
            if not value or isinstance(value[0], str):
                return 'list', value
            if isinstance(value[0], ConfigSection):
                return 'refs', value
        raise errors.ConfigurationError('unsupported type for %r' % (value,))
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
HardCodedConfigSection = currying.partial(
    FakeIncrementalDictConfigSection, convert_asis)
ConfigSectionFromStringDict = currying.partial(
    FakeIncrementalDictConfigSection, convert_string)
AutoConfigSection = currying.partial(
    FakeIncrementalDictConfigSection, convert_hybrid)


def section_alias(target, typename):
    """Build a ConfigSection that instantiates a named reference.

    Because of central's caching our instantiated value will be
    identical to our target's.
    """
    @configurable({'target': 'ref:' + typename}, typename=typename)
    def section_alias(target):
        return target
    return AutoConfigSection({'class': section_alias, 'target': target})


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

def int_parser(string):
    """convert a string to a integer"""
    string = str_parser(string)
    try:
        return int(string)
    except ValueError:
        raise errors.ConfigurationError('%r is not an integer' % string)

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
