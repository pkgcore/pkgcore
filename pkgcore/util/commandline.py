# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Utilities for writing commandline utilities.

pkgcore scripts should use the L{OptionParser} subclass here for a
consistent commandline "look and feel" (and it tries to make life a
bit easier too). They will probably want to use L{main} from an C{if
__name__ == '__main__'} block too: it will take care of things like
consistent exception handling.

See dev-notes/commandline.rst for more complete documentation.
"""


import sys
import optparse
import os.path
import logging

from pkgcore.config import load_config, errors
from snakeoil import formatters, demandload

demandload.demandload(
    globals(),
    'pkgcore:version '
    'pkgcore.config:basics '
    'pkgcore.restrictions:packages '
    'pkgcore.util:parserestrict '
    )


CONFIG_LOADED_MSG = (
    'Configuration already loaded. If moving the option earlier '
    'on the commandline does not fix this report it as a bug.')


class FormattingHandler(logging.Handler):

    """Logging handler printing through a formatter."""

    def __init__(self, formatter):
        logging.Handler.__init__(self)
        # "formatter" clashes with a Handler attribute.
        self.out = formatter

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            color = 'red'
        elif record.levelno >= logging.WARNING:
            color = 'yellow'
        else:
            color = 'cyan'
        first_prefix = (self.out.fg(color), self.out.bold, record.levelname,
                        self.out.reset, ' ', record.name, ': ')
        later_prefix = (len(record.levelname) + len(record.name)) * ' ' + ' : '
        self.out.first_prefix.extend(first_prefix)
        self.out.later_prefix.append(later_prefix)
        try:
            for line in self.format(record).split('\n'):
                self.out.write(line, wrap=True)
        finally:
            self.out.later_prefix.pop()
            for i in xrange(len(first_prefix)):
                self.out.first_prefix.pop()


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
        new_config = dict(
            (name, basics.ConfigSectionFromStringDict(val))
            for name, val in self.new_config.iteritems())
        add_config = {}
        for name, config in self.add_config.iteritems():
            inherit = config.pop('inherit', None)
            # XXX this will likely not be quite correctly quoted.
            if inherit is None:
                config['inherit'] = repr(name)
            else:
                config['inherit'] = '%s %r' % (inherit, name)
            add_config[name] = basics.ConfigSectionFromStringDict(config)
        # Triggers failures if these get mucked with after this point
        # (instead of silently ignoring).
        self.add_config = self.new_config = None
        return load_config(
            debug=self.debug, prepend_sources=(add_config, new_config),
            skip_config_files=self.empty_config)

    @property
    def config(self):
        try:
            return self._config
        except AttributeError:
            self._config = self.load_config()
            return self._config


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


def config_append_callback(option, opt_str, value, parser, typename,
                           typedesc=None):
    """Like L{config_callback} but appends instead of sets."""
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
    for collapsed in config.collapsed_configs.itervalues():
        collapsed.debug = True


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


class Option(optparse.Option):

    def __init__(self, *args, **kwargs):
        self.long_help = kwargs.pop('long_help', None)
        optparse.Option.__init__(self, *args, **kwargs)


class OptionParser(optparse.OptionParser):

    """Our common OptionParser subclass.

    Adds some common options, makes options that get "append"ed
    default to an empty sequence instead of None, uses our custom
    Values class with the config property.
    """

    # You can set this on an instance or subclass to use a different class.
    values_class = Values

    standard_option_list = optparse.OptionParser.standard_option_list + [
        Option(
            '--debug', '-d', action='callback', callback=debug_callback,
            help='print some extra info useful for pkgcore devs. You may have '
            'to set this as first argument for debugging certain '
            'configuration problems.'),
        Option('--nocolor', action='store_true',
            help='disable color in the output.'),
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
        kwargs.setdefault('option_class', Option)
        optparse.OptionParser.__init__(self, *args, **kwargs)
        # It is a callback so it cannot set a default value the "normal" way.
        self.set_default('debug', False)
        self.set_default('empty_config', False)

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
        return self.values_class(defaults)

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
        return values, args

    def convert_to_restrict(self, sequence, default=packages.AlwaysTrue):
        """Convert an iterable to a list of atoms, or return the default"""
        l = []
        try:
            for x in sequence:
                l.append(parserestrict.parse_match(x))
        except parserestrict.ParseError, e:
            self.error("arg %r isn't a valid atom: %s" % (x, e))
        return l or [default]


class MySystemExit(SystemExit):
    """Subclass of SystemExit the tests can safely catch."""


def main(subcommands, args=None, outfile=sys.stdout, errfile=sys.stderr,
         script_name=None):
    """Function to use in an "if __name__ == '__main__'" block in a script.

    Takes one or more combinations of option parser and main func and
    runs them, taking care of exception handling and some other things.

    Any ConfigurationErrors raised from your function (by the config
    manager) are handled. Other exceptions are not (trigger a traceback).

    @type  subcommands: mapping of string => (OptionParser class, main func)
    @param subcommands: available commands.
        The keys are a subcommand name or None for other/unknown/no subcommand.
        The values are tuples of OptionParser subclasses and functions called
        as main_func(config, out, err) with a L{Values} instance, two
        L{snakeoil.formatters.Formatter} instances for output (stdout)
        and errors (stderr). It should return an integer used as
        exit status or None as synonym for 0.
    @type  args: sequence of strings
    @param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    @type  outfile: file-like object
    @param outfile: File to use for stdout, defaults to C{sys.stdout}.
    @type  errfile: file-like object
    @param errfile: File to use for stderr, defaults to C{sys.stderr}.
    @type  script_name: string
    @param script_name: basename of this script, defaults to the basename
        of C{sys.argv[0]}.
    """
    exitstatus = 1
    if args is None:
        args = sys.argv[1:]
    if script_name is None:
        prog = os.path.basename(sys.argv[0])
    else:
        prog = script_name
    parser_class = None
    if args:
        parser_class, main_func = subcommands.get(args[0], (None, None))
        if parser_class is not None:
            prog = '%s %s' % (prog, args[0])
            args = args[1:]
    if parser_class is None:
        try:
            parser_class, main_func = subcommands[None]
        except KeyError:
            # This tries to print in a format very similar to optparse --help.
            errfile.write(
                'Usage: %s <command>\n\nCommands:\n' % (prog,))
            maxlen = max(len(subcommand) for subcommand in subcommands) + 1
            for subcommand, (parser, main) in sorted(subcommands.iteritems()):
                doc = main.__doc__
                if doc is None:
                    errfile.write('  %s\n' % (subcommand,))
                else:
                    doc = doc.split('\n', 1)[0]
                    errfile.write('  %-*s %s\n' % (maxlen, subcommand, doc))
            errfile.write(
                '\nUse --help after a subcommand for more help.\n')
            raise MySystemExit(1)
    options = None
    option_parser = parser_class(prog=prog)
    out = None
    try:
        options, args = option_parser.parse_args(args)
        # Checked here and not in OptionParser because we want our
        # check_values to run before the user's, not after it.
        if args:
            option_parser.error("I don't know what to do with %s" %
                                (' '.join(args),))
        else:
            if options.nocolor:
                formatter_factory = formatters.PlainTextFormatter
            else:
                formatter_factory = formatters.get_formatter
            out = formatter_factory(outfile)
            err = formatter_factory(errfile)
            if logging.root.handlers:
                # Remove the default handler.
                logging.root.handlers.pop(0)
            logging.root.addHandler(FormattingHandler(err))
            exitstatus = main_func(options, out, err)
    except errors.ConfigurationError, e:
        if options is not None and options.debug:
            raise
        errfile.write('Error in configuration:\n%s\n' % (e,))
    except KeyboardInterrupt:
        if options is not None and options.debug:
            raise
    if out is not None:
        if exitstatus:
            out.title('%s failed' % (prog,))
        else:
            out.title('%s succeeded' % (prog,))
    raise MySystemExit(exitstatus)
