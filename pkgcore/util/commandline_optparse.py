# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Utilities for writing commandline utilities.

pkgcore scripts should use the :obj:`OptionParser` subclass here for a
consistent commandline "look and feel" (and it tries to make life a
bit easier too). They will probably want to use :obj:`main` from an C{if
__name__ == '__main__'} block too: it will take care of things like
consistent exception handling.

See dev-notes/commandline.rst for more complete documentation.
"""

__all__ = ("Values", "Option", "OptionParser",
    "read_file_callback", "config_callback",
    "domain_callback", "config_append_callback",
    "debug_callback", "new_config_callback", "empty_config_callback",
    "convert_bool_type",
    "optparse_parse", "MySystemExit",
)

import sys
import os.path
import logging

from pkgcore.config import load_config
from snakeoil import demandload, klass
import optparse
import copy

demandload.demandload(globals(),
    'snakeoil.bash:iter_read_bash',
    'pkgcore:version',
    'pkgcore.config:basics',
    'pkgcore.util:parserestrict',
    'pkgcore.ebuild:atom',
)


CONFIG_LOADED_MSG = (
    'Configuration already loaded. If moving the option earlier '
    'on the commandline does not fix this report it as a bug.')


# Mix in object here or properties do not work (Values is an oldstyle class).
class Values(optparse.Values, object):

    """Values with an autoloaded config property.

    If you do not want the config autoloaded you can set the _config
    attribute like this:

     >>> parser = OptionParser()
     >>> vals = parser.get_default_values()
     >>> vals._config = my_custom_central
     >>> parser.parse_args(args, vals)
    """

    def __init__(self, defaults=None):
        optparse.Values.__init__(self, defaults)
        self.new_config = {}
        self.add_config = {}

    def load_config(self):
        """Override this if you need a different way of loading config."""
        # This makes mixing --new-config and --add-config sort of
        # work. Not sure if that is a good thing, but detecting and
        # erroring is about as much work as making it mostly work :)
        new_config = {
            name: basics.ConfigSectionFromStringDict(val)
            for name, val in self.new_config.iteritems()}
        add_config = {}
        for name, config in self.add_config.iteritems():
            config.setdefault('inherit', name)
            add_config[name] = basics.ConfigSectionFromStringDict(config)
        # Triggers failures if these get mucked with after this point
        # (instead of silently ignoring).
        self.add_config = self.new_config = None
        return load_config(
            debug=self.debug, append_sources=(new_config, add_config),
            skip_config_files=self.empty_config)

    def load_domain(self):
        """Override this if you need to change the default domain logic."""
        domain = self.config.get_default('domain')
        if domain is None:
            self._raise_error(
                'No default domain found, fix your configuration '
                'or pass --domain (valid domains: %s)' % (
                ', '.join(self.config.domain),))
        return domain

    config = klass.jit_attr_ext_method("load_config", "_config",
        uncached_val=None)
    domain = klass.jit_attr_ext_method("load_domain", "_domain",
        uncached_val=None)

    def get_pkgset(self, err, setname, config=None):
        if config is None:
            config = self.config
        try:
            return config.pkgset[setname]
        except KeyError:
            if err:
                err.write('No set called %r!\nknown sets: %r' %
                         (setname, sorted(config.pkgset.keys())))
            return None


def read_file_callback(option, opt_str, value, parser):
    """Read a file ignoring comments."""
    if not os.path.isfile(value):
        raise optparse.OptionValueError("'%s' is not a file" % value)
    setattr(parser.values, option.dest, iter_read_bash(value))


def config_callback(option, opt_str, value, parser, typename, typedesc=None):
    """Retrieve a config section.

    Pass the typename of the section as callback_args=('typename',),
    and set type='string'. You can optionally pass a human-readable
    typename as second element of callback_args.
    """
    if typedesc is None:
        typedesc = typename
    mapping = getattr(parser.values.config, typename)
    try:
        result = mapping[value]
    except KeyError:
        raise optparse.OptionValueError(
            '%r is not a valid %s for %s (valid values: %s)' % (
                value, typedesc, opt_str, ', '.join(repr(key)
                                                    for key in mapping)))
    setattr(parser.values, option.dest, result)


def domain_callback(option, opt_str, value, parser):
    """Retrieve a specified domain
    """

    try:
        parser.values._domain = parser.values.config.domain[value]
    except KeyError:
        raise optparse.OptionValueError(
            '%r is not a valid domain (valid values: %s)' % (
                value, ', '.join(repr(key)
                    for key in parser.values.config.domain)))


def debug_callback(option, opt_str, value, parser):
    """Make sure the config central uses debug mode.

    We do this because it is possible to access config from an option
    callback before the entire commandline is parsed. This callback
    makes sure any config usage after optparse hit the --debug switch
    is properly in debug mode.

    Ideally we would not need this, since needing this means things
    accessing config too early still get the wrong debug setting. But
    doing that would mean either (crappily) parsing the commandline
    before optparse does or making config access from option callbacks
    illegal. The former is hard to get "right" (impossible to get
    completely "right" since you cannot know how many arguments an
    option with a callback consumes without calling it) and the latter
    is unwanted because accessing config from callbacks is useful
    (pcheck will do this at the time of writing).
    """
    parser.values.debug = True
    config = parser.values.config
    config.debug = True
    logging.root.setLevel(logging.DEBUG)
    for collapsed in config.rendered_sections.itervalues():
        collapsed.debug = True


def config_append_callback(option, opt_str, value, parser, typename,
                           typedesc=None):
    """Like :obj:`config_callback` but appends instead of sets."""
    if typedesc is None:
        typedesc = typename
    mapping = getattr(parser.values.config, typename)
    try:
        result = mapping[value]
    except KeyError:
        raise optparse.OptionValueError(
            '%r is not a valid %s for %s (valid values: %s)' % (
                value, typedesc, opt_str, ', '.join(repr(key)
                                                    for key in mapping)))
    parser.values.ensure_value(option.dest, []).append(result)


def new_config_callback(option, opt_str, value, parser):
    """Add a configsection to our values object.

    Munges three arguments: section name, key name, value.

    dest defines an attr name on the values object to store in.
    """
    if getattr(parser.values, '_config', None) is not None:
        raise optparse.OptionValueError(CONFIG_LOADED_MSG)
    section_name, key, val = value
    section = getattr(parser.values, option.dest).setdefault(section_name, {})
    if key in section:
        raise optparse.OptionValueError(
            '%r is already set (to %r)' % (key, section[key]))
    section[key] = val


def empty_config_callback(option, opt_str, value, parser):
    """Remember not to load the user/system configuration.

    Error out if we have already loaded it.
    """
    if getattr(parser.values, '_config', None) is not None:
        raise optparse.OptionValueError(CONFIG_LOADED_MSG)
    parser.values.empty_config = True


def convert_bool_type(option, opt, value):
    v = value.lower()
    if v in ("true", "y", "yes"):
        return True
    elif v in ("false", "n", "no"):
        return False
    raise optparse.OptionValueError("option %s: invalid bool value: %r."
        "  Valid values are %r" % (opt, value,
        sorted(("true", "false", "y", "yes", "n", "no"))))

class Option(optparse.Option):

    TYPES = optparse.Option.TYPES + ('bool',)
    TYPE_CHECKER = optparse.Option.TYPE_CHECKER.copy()
    TYPE_CHECKER['bool'] = convert_bool_type

    def __init__(self, *args, **kwargs):
        self.long_help = kwargs.pop('long_help', None)
        optparse.Option.__init__(self, *args, **kwargs)


class ProtectiveCopy(type):

    def __call__(cls, *args, **kwds):
        # always clone standard_options_list if it exists...
        # we do not want the raw option being used, period,
        # else you'll get bleed through of instances.
        instance = cls.__new__(cls,*args, **kwds)
        if instance.standard_option_list:
            l = []
            for option in instance.standard_option_list:
                copier = getattr(option, 'copy', None)
                if copier is None:
                    l.append(copy.copy(option))
                else:
                    l.append(copier())
            instance.standard_option_list = l
        instance.__init__(*args, **kwds)
        return instance



class OptionParser(optparse.OptionParser, object):

    """Our common OptionParser subclass.

    Adds some common options, makes options that get "append"ed
    default to an empty sequence instead of None, uses our custom
    Values class with the config property.
    """

    __metaclass__ = ProtectiveCopy

    # You can set this on an instance or subclass to use a different class.
    values_class = Values

    enable_domain_options = False
    description = None
    usage = None
    option_class = Option
    arguments_allowed = False

    standard_option_list = optparse.OptionParser.standard_option_list + [
        Option(
            '--debug', '-d', action='callback', callback=debug_callback,
            help='print some extra info useful for pkgcore devs. You may have '
            'to set this as first argument for debugging certain '
            'configuration problems.'),
        Option('--color', action='store', type='bool', default=True,
            help='enable/disable color', metavar='BOOLEAN'),
        Option('--nocolor', action='store_false', dest='color',
            help='alias for --color=n'),
        Option('--version', action='version'),
        Option(
            '--add-config', action='callback', callback=new_config_callback,
            type='str', nargs=3, help='Add a new configuration section. '
            'Takes three arguments: section name, value name, value.'),
        Option(
            '--new-config', action='callback', callback=new_config_callback,
            type='str', nargs=3, help='Expand a configuration section. '
            'Just like --add-config but with an implied inherit=sectionname.'),
        Option(
            '--empty-config', action='callback',
            callback=empty_config_callback,
            help='Do not load the user or system configuration. Can be useful '
            'combined with --new-config.')
        ]

    def __init__(self, *args, **kwargs):
        """Initialize."""
        kwargs.setdefault('option_class', self.option_class)
        for setting in ('description', 'usage'):
            if not setting in kwargs and hasattr(self, setting):
                # only set if not overridden, and if there is a usable value.
                kwargs[setting] = getattr(self, setting)

        optparse.OptionParser.__init__(self, *args, **kwargs)
        # It is a callback so it cannot set a default value the "normal" way.
        self.set_default('debug', False)
        self.set_default('empty_config', False)
        if self.enable_domain_options:
            self.add_option('--domain', action='callback', type='string',
                callback=domain_callback,
                help='domain name to use (default used if omitted).',
                dest='_domain')
        self._register_options()

    def _register_options(self):
        pass

    def get_version(self):
        """Add pkgcore's version to the version information."""
        ver = optparse.OptionParser.get_version(self)
        pkgcore_ver = version.get_version()
        if ver:
            return '\n'.join((ver, pkgcore_ver))
        return pkgcore_ver

    def print_version(self, file=None):
        """Print the version to a filelike (defaults to stdout).

        Overridden because the optparse one is a noop if self.version is false.
        """
        print >> file, self.get_version()

    def _add_version_option(self):
        """Override this to be a no-op.

        Needed because optparse does not like our on-demand generation
        of the version string.
        """

    def get_default_values(self):
        """Slightly simplified copy of optparse code using our Values class."""
        # Needed because optparse has the Values class hardcoded in
        # (and no obvious way to get the defaults set on an existing
        # Values instance).
        defaults = self.defaults.copy()
        for option in self._get_all_options():
            default = defaults.get(option.dest)
            if isinstance(default, basestring):
                opt_str = option.get_opt_string()
                defaults[option.dest] = option.check_value(opt_str, default)
        defaults["prog_name"] = self.get_prog_name()
        return self.values_class(defaults)

    def parse_restrict(self, arg, msg=None, eapi=None):
        if eapi is not None:
            return self.parse_atom(arg, msg=msg, eapi=eapi)
        try:
            return parserestrict.parse_match(arg)
        except parserestrict.ParseError as e:
            if msg is None:
                msg="couldn't parse restriction from %(arg)s: %(error)s"
            self.error(msg % {"arg":arg, "error": e})

    def parse_atom(self, arg, msg=None, eapi=-1):
        try:
            return atom.atom(arg, eapi=eapi)
        except atom.MalformedAtom as ma:
            if msg is None:
                msg="couldn't parse valid atom from %(arg)s: %(error)s"
            self.error(msg % {"arg":arg, "error":ma})

    def parse_args(self, args=None, values=None):
        """Extend optparse to clear the ref values -> parser it adds."""
        try:
            values, args = optparse.OptionParser.parse_args(self, args, values)
            if self.arguments_allowed:
                values.arguments = tuple(args)
                return values, ()
            return values, args
        finally:
            self.values = None

    def check_values(self, values, args):
        """Do some basic sanity checking.

        optparse defaults unset lists to None. An empty sequence is
        much more convenient (lets you use them in a for loop without
        a None check) so we fix those up (based on action "append").
        """
        for container in self.option_groups + [self]:
            for option in container.option_list:
                if option.action == 'append':
                    values.ensure_value(option.dest, [])
        # domain option specifically needs to chuck an error on jit'd access,
        # hence giving a backref to it.
        values._raise_error = self.error
        return self._check_values(values, args)

    def _check_values(self, values, args):
        return values, args


class MySystemExit(SystemExit):
    """Subclass of SystemExit the tests can safely catch."""


def output_subcommands(prog, subcommands, out):
    # This tries to print in a format very similar to optparse --help.
    out.write('Usage: %s <command>\n\n' % (prog,))
    if subcommands:
        out.write('Commands:\n')
        maxlen = max(len(subcommand) for subcommand in subcommands) + 1
        for subcommand, parser_data in sorted(subcommands.iteritems()):
            if hasattr(parser_data, 'get'):
                out.write('  %-*s %s\n' % (maxlen, subcommand,
                    'subcommands related to ' + subcommand))
                continue
            try:
                parser_class, main_func = parser_data
            except TypeError:
                main_func = parser_data.run
                parser_class = parser_data
            doc = main_func.__doc__
            if not doc:
                doc = getattr(parser_class, 'description', None)
            if doc is None:
                out.write('  %s\n' % (subcommand,))
            else:
                doc = doc.split('\n', 1)[0]
                out.write('  %-*s %s\n' % (maxlen, subcommand, doc))
        out.write(
            '\nUse --help after a subcommand for more help.\n')
    else:
        out.write("no commands available\n")


def optparse_parse(subcommands, args=None, script_name=None,
                   subcommand_usage_func=output_subcommands, errfile=None):
    """Function to use in an "if __name__ == '__main__'" block in a script.

    Takes one or more combinations of option parser and main func and
    runs them, taking care of exception handling and some other things.

    Any ConfigurationErrors raised from your function (by the config
    manager) are handled. Other exceptions are not (trigger a traceback).

    :type subcommands: mapping of string => (OptionParser class, main func)
    :param subcommands: available commands.
        The keys are a subcommand name or None for other/unknown/no subcommand.
        The values are tuples of OptionParser subclasses and functions called
        as main_func(config, out, err) with a :obj:`Values` instance, two
        :obj:`snakeoil.formatters.Formatter` instances for output (stdout)
        and errors (stderr). It should return an integer used as
        exit status or None as synonym for 0.
    :type args: sequence of strings
    :param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    :type script_name: string
    :param script_name: basename of this script, defaults to the basename
        of C{sys.argv[0]}.
    """
    if args is None:
        args = sys.argv[1:]
    if script_name is None:
        prog = os.path.basename(sys.argv[0])
    else:
        prog = script_name

    parser_class = None
    while args:
        new_parser_class = subcommands.get(args[0], None)
        if new_parser_class is None:
            break
        prog = '%s %s' % (prog, args[0])
        args = args[1:]
        if hasattr(new_parser_class, 'get'):
            subcommands = new_parser_class
        else:
            parser_class = new_parser_class
    if parser_class is None:
        parser_class = subcommands.get(None, (None, None))

    main_func = None
    try:
        parser_class, main_func = parser_class
    except TypeError:
        # ok... so it's new style, or None
        pass

    if parser_class is None:
        subcommand_usage_func(prog, subcommands, errfile)
        raise MySystemExit(1)

    options = None
    option_parser = parser_class(prog=prog)
    options, args = option_parser.parse_args(args)
    # Checked here and not in OptionParser because we want our
    # check_values to run before the user's, not after it.
    if args:
        option_parser.error("I don't know what to do with %s" %
                           (' '.join(args),))
        raise MySystemExit(1)
    if not hasattr(options, 'prog'):
        options.prog = prog
    if main_func is None:
        main_func = getattr(option_parser, 'run', None)
        if main_func is None:
            raise Exception("internal error; OptParser parser %s doesn't have "
                "any specified main" % (option_parser,))
    return main_func, options
