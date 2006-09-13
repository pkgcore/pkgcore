# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""
configuration subsystem primitives

all callables can/may throw a
L{configuration exception<pkgcore.config.errors.ConfigurationError>}
"""


from pkgcore.config import errors
from pkgcore.util.demandload import demandload
demandload(globals(),
    "pkgcore.util:modules ")

type_names = (
    "list", "str", "bool", "section_ref", "section_refs", "section_name")


class ConfigType(object):

    """A configurable 'type"""

    def __init__(self, typename, types, positional=None, incrementals=None, \
        required=None, defaults=None, allow_unknowns=False):

        """
        @param typename: name of the type, used in errors.
        @param types: dict mapping key names to type strings.
        @param positional: container holding positional arguments.
        @param incrementals: container holding incrementals.
        @param required: container holding required arguments.
        @param defaults: L{ConfigSection} with default values.
        @param allow_unknowns: controls whether unknown settings should error.
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
        self.allow_unknowns = bool(allow_unknowns)

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

    def get_section_ref(self, central, section, msg):
        assert central is not None
        if not isinstance(section, basestring):
            raise errors.ConfigurationError(msg % (
                    "got section %r which isn't a basestring; indicates "
                    "HardCodedConfigSection definition is broke" % (section,)))
        try:
            conf = central.get_section_config(section)
        except KeyError:
            raise errors.ConfigurationError(msg % 'not found')
        try:
            return central.instantiate_section(section, conf=conf)
        except (SystemExit, KeyboardInterrupt, AssertionError):
            raise
        except errors.ConfigurationError:
            raise
        except Exception, e:
            s = "Exception " + str(e)
            raise errors.ConfigurationError(msg % s)



class ConfigSectionFromStringDict(ConfigSection):

    """Useful for string-based config implementations."""

    def __init__(self, name, source_dict):
        ConfigSection.__init__(self)
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
                    '%r: cannot import %r' % (self.name, value))
            if not callable(func):
                raise errors.ConfigurationError(
                    '%r: %r is not callable' % (self.name, value))
            return func
        elif arg_type == 'section_refs':
            result = []
            if "cache" in value:
                print value, list_parser(value)
            value = list_parser(value)
            for x in value:
                result.append(self.get_section_ref(
                        central, x,
                        "%r: requested section refs %r for section %r, "
                        "section %r: error %%s" %
                        (self.name, value, name, x)))
            return result
        elif arg_type == 'section_ref':
            value = str_parser(value)
            return self.get_section_ref(central, value,
                "%r: requested section ref %r for section %r: error %%s" %
                (self.name, name, value))
        return {
            'list': list_parser,
            'str': str_parser,
            'bool': bool_parser,
            }[arg_type](value)


class HardCodedConfigSection(ConfigSection):

    """Just wrap around a dict."""

    def __init__(self, name, source_dict):
        ConfigSection.__init__(self)
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
                try:
                    value = modules.load_attribute(value)
                except modules.FailedImport:
                    raise errors.ConfigurationError(
                        '%r: cannot import %r' % (self.name, value))
                if not callable(value):
                    raise errors.ConfigurationError(
                        '%r: %r is not callable' % (self.name, value))

        elif arg_type == 'section_ref':
            value = self.get_section_ref(central, value,
                "%r: requested section %r for section %r: error %%s" %
                (self.name, name, value))

        elif arg_type == 'section_refs':
            l = []
            for x in value:
                l.append(self.get_section_ref(
                        central, x,
                        "%r: requested section refs %r for section %r, "
                        "section ref %r: error %%s" %
                        (self.name, value, name, x)))
            value = l

        elif not isinstance(value, types[arg_type]):
            raise errors.ConfigurationError(
                '%s: %r does not have type %r' % (self.name, name, arg_type))

        return value

def SectionAlias(new_section, section):
    """convience function to generate a section alias
    @param new_section: str name of the new section
    @param section: str name of the section to alias
    @return: L{ConfigSectionFromStringDict}
    """
    return ConfigSectionFromStringDict(new_section,
        {"type": "alias", "section": section})


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
