"""
configuration subsystem primitives

all callables can/may throw a :class:`pkgcore.config.errors.ConfigurationError`
"""

__all__ = (
    "ConfigType",
    "LazySectionRef",
    "LazyNamedSectionRef",
    "ConfigSection",
    "DictConfigSection",
    "convert_string",
    "convert_asis",
    "convert_hybrid",
    "section_alias",
    "str_to_list",
    "str_to_str",
    "str_to_bool",
    "str_to_int",
    "parse_config_file",
)

import typing
from functools import partial

from snakeoil import modules
from snakeoil.compatibility import IGNORED_EXCEPTIONS

from . import errors
from .hint import configurable

type_names = ("list", "str", "bool", "int")


# Copied from inspect.py which copied it from compile.h.
# Also documented in http://docs.python.org/ref/types.html.
CO_VARARGS, CO_VARKEYWORDS = 4, 8


class ConfigType:
    """A configurable type.

    :ivar name: string specifying the protocol the instantiated object
        conforms to.
    :ivar callable: callable used to instantiate this type.
    :ivar types: dict mapping key names to type strings.
    :ivar positional: container holding positional arguments.
    :ivar required: container holding required arguments.
    :ivar allow_unknowns: controls whether unknown settings should error.
    """

    callable: typing.Callable
    types: dict[str, str]
    positional: tuple[str]
    required: tuple[str]
    allow_unknowns: bool

    def __init__(self, func_obj: typing.Callable) -> None:
        """Create from a callable (function, member function, class).

        It uses the defaults to determine type:
         - True or False mean it's a boolean
         - a tuple means it's a list (of strings)
         - a str means it's a string

        Arguments with a default of a different type are ignored.

        If an argument has no default, it is assumed to be a string-
        exception to this is if the callable has a pkgcore_config_type
        attr that is a :obj:`ConfigHint` instance, in which case those
        override.
        """
        original_func_obj = func_obj
        self.name = func_obj.__name__
        self.callable = func_obj
        self.doc = getattr(func_obj, "__doc__", None)
        if not hasattr(func_obj, "__code__"):
            # No function or method, should be a class so grab __init__.
            func_obj = func_obj.__init__
        # We do not use the inspect module because that is a heavy
        # thing to import and we can pretty easily get the data we
        # need without it. Most of the code in its getargs function
        # deals with tuples inside argument definitions, which we do
        # not support anyway.
        #
        # TODO: use the inspect module, speed is less of an issue in 2023.
        self.types = {}

        varargs, args, defaults, varkw = (), (), (), ()
        hint_overrides = getattr(self.callable, "pkgcore_config_type", None)
        # if it's not authorative, do introspection; the getattr is to protect
        # against the case where there is no Hint
        if not getattr(hint_overrides, "authorative", None):
            try:
                code = getattr(func_obj, "__code__")
            except AttributeError as e:
                if func_obj != object.__init__:
                    raise TypeError(
                        f"func {original_func_obj!r} isn't usable; likely a "
                        "builtin object which can't be introspected without hints"
                    ) from e
            else:
                if code.co_argcount and code.co_varnames[0] == "self":
                    args = code.co_varnames[1 : code.co_argcount]
                else:
                    args = code.co_varnames[: code.co_argcount]
                varargs = bool(code.co_flags & CO_VARARGS)
                varkw = bool(code.co_flags & CO_VARKEYWORDS)
                defaults = func_obj.__defaults__
                if defaults is None:
                    defaults = ()
                # iterate through defaults backwards, so they match up to argnames
                for i, default in enumerate(reversed(defaults)):
                    argname = args[-1 - i]
                    for typeobj, typename in [
                        (bool, "bool"),
                        (tuple, "list"),
                        (str, "str"),
                        (int, "int"),
                    ]:
                        if isinstance(default, typeobj):
                            self.types[argname] = typename
                            break
        # just [:-len(defaults)] doesn't work if there are no defaults
        self.positional = args[: len(args) - len(defaults)]
        # no defaults to determine the type from -> default to str.
        for arg in self.positional:
            self.types[arg] = "str"
        self.required = tuple(self.positional)
        self.allow_unknowns = False
        self.requires_config = False
        self.raw_class = False

        # Process ConfigHint (if any)
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
            self.requires_config = hint_overrides.requires_config
            self.raw_class = hint_overrides.raw_class
            if self.requires_config:
                if self.requires_config in self.required:
                    self.required = tuple(
                        x for x in self.required if x != self.requires_config
                    )
        elif varargs or varkw:
            raise TypeError(
                f"func {self.callable} accepts *args or **kwargs, "
                "and no ConfigHint is provided"
            )

        for var in ("class", "inherit", "default"):
            if var in self.types:
                raise errors.TypeDefinitionError(
                    f"{self.callable}: you cannot change the type of {var!r}"
                )

        for var in self.positional:
            if var not in self.required and var != self.requires_config:
                raise errors.TypeDefinitionError(
                    f"{self.callable}: {var!r} is in positionals but not in required"
                )


class LazySectionRef:
    """Abstract base class for lazy-loaded section references."""

    typename: str

    def __init__(self, central, typename: str) -> None:
        self.central = central
        self.typename = typename.split(":", 1)[1]
        self.cached_config = None

    def _collapse(self):
        """Override this in a subclass."""
        raise NotImplementedError(self._collapse)

    def collapse(self):
        """:return: :obj:`pkgcore.config.central.CollapsedConfig`."""
        if self.cached_config is None:
            config = self.cached_config = self._collapse()
            if self.typename is not None and config.type.name != self.typename:
                raise errors.ConfigurationError(
                    f"reference {self.name!r} should be of type "
                    f"{self.typename!r}, got {config.type.name!r}"
                )
        return self.cached_config

    def instantiate(self) -> typing.Any:
        """Convenience method returning the instantiated section."""
        return self.collapse().instantiate()


class LazyNamedSectionRef(LazySectionRef):
    name: str

    def __init__(self, central, typename: str, name: str) -> None:
        super().__init__(central, typename)
        self.name = name

    def _collapse(self):
        return self.central.collapse_named_section(self.name)


class LazyUnnamedSectionRef(LazySectionRef):
    def __init__(self, central, typename: str, section) -> None:
        super().__init__(central, typename)
        self.section = section

    def _collapse(self):
        return self.central.collapse_section([self.section])


class ConfigSection:
    """Single Config section, returning typed values from a key.

    Not much of an object this, if we were using zope.interface it'd
    be an Interface.
    """

    def __contains__(self, name: str) -> bool:
        """Check if a key is in this section."""
        raise NotImplementedError(self.__contains__)

    def keys(self) -> list[str]:
        """Return a list of keys."""
        raise NotImplementedError(self.keys)

    def render_value(self, central, name: str, arg_type):
        """Return a setting, converted to the requested type."""
        raise NotImplementedError(self, "render_value")


class DictConfigSection(ConfigSection):
    """Turns a dict and a conversion function into a ConfigSection."""

    func: typing.Callable
    dict: dict[str, typing.Any]

    def __init__(
        self, conversion_func: typing.Callable, source_dict: dict[str, typing.Any]
    ) -> None:
        """Initialize.

        The conversion func should return a single sequence for list types and in
        repr for list types.

        :type conversion_func: callable.
        :param conversion_func: called with a ConfigManager, a value from
            the dict and a type name.
        :type source_dict: dict with string keys and arbitrary values.
        """
        super().__init__()
        self.func = conversion_func
        self.dict = source_dict

    def __contains__(self, name: str) -> bool:
        return name in self.dict

    def keys(self) -> list[str]:
        return list(self.dict.keys())

    def render_value(
        self, central, name: str, arg_type: str
    ) -> typing.Union[typing.Any, tuple[str, typing.Any]]:
        try:
            return self.func(central, self.dict[name], arg_type)
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            raise errors.ConfigurationError(
                f"Failed converting argument {name!r} to {arg_type}"
            ) from e


def str_to_list(string: str) -> list[str]:
    """Split on whitespace honoring quoting for new tokens."""
    # TODO: replace this with shlex or equivalent parsing.
    l = []
    i = 0
    e = len(string)
    # check for stringness because we return something interesting if
    # feeded a sequence of strings
    if not isinstance(string, str):
        raise TypeError(f"expected a string, got {string!r}")
    while i < e:
        if not string[i].isspace():
            if string[i] in ("'", '"'):
                q = i
                i += 1
                res = []
                while i < e and string[i] != string[q]:
                    if string[i] == "\\":
                        i += 1
                    res.append(string[i])
                    i += 1
                if i >= e:
                    raise errors.QuoteInterpretationError(string)
                l.append("".join(res))
            else:
                res = []
                while i < e and not (string[i].isspace() or string[i] in ("'", '"')):
                    if string[i] == "\\":
                        i += 1
                    res.append(string[i])
                    i += 1
                if i < e and string[i] in ("'", '"'):
                    raise errors.QuoteInterpretationError(string)
                l.append("".join(res))
        i += 1
    return l


def str_to_str(string: str) -> str:
    """Yank leading/trailing whitespace and quotation, along with newlines."""
    # TODO: replace these with shlex
    s = string.strip()
    if len(s) > 1 and s[0] in "\"'" and s[0] == s[-1]:
        s = s[1:-1]
    return s.replace("\n", " ").replace("\t", " ")


def str_to_bool(string: str) -> bool:
    """Convert a string to a boolean."""
    s = str_to_str(string).lower()
    if s in ("no", "false", "0"):
        return False
    if s in ("yes", "true", "1"):
        return True
    raise errors.ConfigurationError(f"{s!r} is not a boolean")


def str_to_int(string: str) -> int:
    """Convert a string to a integer."""
    string = str_to_str(string)
    try:
        return int(string)
    except ValueError:
        raise errors.ConfigurationError(f"{string!r} is not an integer")


_str_converters = {
    "list": str_to_list,
    "str": str_to_str,
    "bool": str_to_bool,
    "int": str_to_int,
}


def convert_string(central, value, arg_type: str):
    """Conversion func for a string-based DictConfigSection."""
    if not isinstance(value, str):
        raise ValueError(
            "convert_string invoked with non str instance: "
            f"val({value!r}), arg_type({arg_type!r})"
        )
    if arg_type == "callable":
        try:
            func = modules.load_attribute(value)
        except modules.FailedImport as e:
            raise errors.ConfigurationError(f"cannot import {value!r}") from e
        if not callable(func):
            raise errors.ConfigurationError(f"{value!r} is not callable")
        return func
    elif arg_type.startswith("refs:"):
        return list(
            LazyNamedSectionRef(central, arg_type, ref) for ref in str_to_list(value)
        )
    elif arg_type.startswith("ref:"):
        return LazyNamedSectionRef(central, arg_type, str_to_str(value))
    elif arg_type == "repr":
        return "str", value
    func = _str_converters.get(arg_type)
    if func is None:
        raise errors.ConfigurationError(f"unknown type {arg_type!r}")
    return func(value)


def convert_asis(central, value, arg_type: str):
    """ "Conversion" func assuming the types are already correct."""
    if arg_type == "callable":
        if not callable(value):
            raise errors.ConfigurationError(f"{value!r} is not callable")
        return value
    elif arg_type.startswith("ref:"):
        if not isinstance(value, ConfigSection):
            raise errors.ConfigurationError(f"{value!r} is not a config section")
        return LazyUnnamedSectionRef(central, arg_type, value)
    elif arg_type.startswith("refs:"):
        l = []
        for section in value:
            if not isinstance(section, ConfigSection):
                raise errors.ConfigurationError(f"{value!r} is not a config section")
            l.append(LazyUnnamedSectionRef(central, arg_type, section))
        return l
    elif arg_type == "repr":
        if callable(value):
            return "callable", value
        if isinstance(value, ConfigSection):
            return "ref", value
        if isinstance(value, str):
            return "str", value
        if isinstance(value, bool):
            return "bool", value
        if isinstance(value, (list, tuple)):
            if not value or isinstance(value[0], str):
                return "list", value
            if isinstance(value[0], ConfigSection):
                return "refs", value
        raise errors.ConfigurationError(f"unsupported type for {value!r}")
    elif not isinstance(
        value, {"list": (list, tuple), "str": str, "bool": bool}[arg_type]
    ):
        raise errors.ConfigurationError(f"{value!r} does not have type {arg_type!r}")
    return value


def convert_hybrid(central, value, arg_type: str):
    """Automagically switch between :obj:`convert_string` and :obj:`convert_asis`.

    :obj:`convert_asis` is used for arg_type str and if value is not a string.
    :obj:`convert_string` is used for the rest.

    Be careful about handing in escaped strings: they are not
    unescaped (for arg_type str).
    """
    if arg_type != "str" and isinstance(value, str):
        return convert_string(central, value, arg_type)
    return convert_asis(central, value, arg_type)


# "Invalid name" (pylint thinks these are module-level constants)
# pylint: disable-msg=C0103
HardCodedConfigSection = partial(DictConfigSection, convert_asis)
ConfigSectionFromStringDict = partial(DictConfigSection, convert_string)
AutoConfigSection = partial(DictConfigSection, convert_hybrid)


def section_alias(target, typename: str) -> AutoConfigSection:
    """Build a ConfigSection that instantiates a named reference.

    Because of central's caching our instantiated value will be
    identical to our target's.
    """

    @configurable(types={"target": "ref:" + typename}, typename=typename)
    def section_alias(target):
        return target

    return AutoConfigSection({"class": section_alias, "target": target})


@configurable(types={"path": "str", "parser": "callable"}, typename="configsection")
def parse_config_file(path: str, parser):
    try:
        f = open(path, "r")
    except (IOError, OSError) as e:
        raise errors.InstantiationError(f"failed opening {path!r}") from e
    try:
        return parser(f)
    finally:
        f.close()


class ConfigSource:
    description = "No description available"

    def sections(self):
        raise NotImplementedError(self, "sections")


class GeneratedConfigSource(ConfigSource):
    def __init__(self, section_data, description: str) -> None:
        self.description = description
        self.section_data = section_data

    def sections(self):
        return self.section_data
