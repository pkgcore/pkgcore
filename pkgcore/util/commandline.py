# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Utilities for writing commandline utilities.

pkgcore scripts should use the L{OptionParser} subclass here for a
consistent commandline "look and feel" (and it tries to make life a
bit easier too). They will probably want to use L{main} from an C{if
__name__ == '__main__'} block too: it will take care of things like
consistent exception handling.
"""


import sys
import optparse
import os.path

from pkgcore.config import load_config, errors

from pkgcore.util import formatters


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

    def load_config(self):
        """Override this if you need a different way of loading config."""
        return load_config(debug=self.debug)

    @property
    def config(self):
        try:
            return self._config
        except AttributeError:
            self._config = self.load_config()
            return self._config


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
    for collapsed in config.collapsed_configs.itervalues():
        collapsed.debug = True


class OptionParser(optparse.OptionParser):

    """Our common OptionParser subclass.

    Adds some common options, makes options that get "append"ed
    default to an empty sequence instead of None, uses our custom
    Values class with the config property.
    """

    # You can set this on an instance or subclass to use a different class.
    values_class = Values

    standard_option_list = optparse.OptionParser.standard_option_list + [
        optparse.Option(
            '--debug', '-d', action='callback', callback=debug_callback,
            help='print some extra info useful for pkgcore devs. You may have '
            'to set this as first argument for debugging certain '
            'configuration problems.'),
        optparse.Option('--nocolor', action='store_true',
                        help='disable color in the output.'),
        ]

    def __init__(self, *args, **kwargs):
        """Initialize."""
        optparse.OptionParser.__init__(self, *args, **kwargs)
        # It is a callback so it cannot set a default value the "normal" way.
        self.set_default('debug', False)

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
        """Do some basic sanity checking."""
        # optparse defaults unset lists to None. An empty sequence is
        # much more convenient (lets you use them in a for loop
        # without a None check) so fix those up:
        for container in self.option_groups + [self]:
            for option in container.option_list:
                if option.action == 'append':
                    values.ensure_value(option.dest, [])
        return values, args


def main(subcommands, args=None, sys_exit=True):
    """Function to use in an "if __name__ == '__main__'" block in a script.

    Options are parsed before the config is loaded. This means you
    should do any extra validation of options that you do not need the
    config for in check_values of your option parser (if that fails
    the config is never loaded, so it will be faster).

    Handling the unparsed "args" from the option parser should be done
    in check_values too (added to the values object). Unhandled args
    are treated as an error by this function.

    Any ConfigurationErrors raised from your function (by the config
    manager) are handled. Other exceptions are not (trigger a traceback).

    @type  subcommands: mapping of string => (OptionParser class, main func)
    @param subcommands: available commands.
        The keys are a subcommand name or None for other/unknown/no subcommand.
        The values are tuples of OptionParser subclasses and functions called
        as main_func(config, out, err) with a L{Values} instance, a
        L{pkgcore.util.formatters.Formatter} for output and a filelike
        for errors (C{sys.stderr}). It should return an integer used as
        exit status or None as synonym for 0.
    @type  args: sequence of strings
    @param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    @type  sys_exit: boolean
    @param sys_exit: if True C{sys.exit} is called when done, otherwise
        the exitstatus is returned.
    """
    if args is None:
        args = sys.argv[1:]
    prog = os.path.basename(sys.argv[0])
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
            if not sys_exit:
                return 1
            # This tries to print in a format very similar to optparse --help.
            sys.stderr.write(
                'Usage: %s <command>\n\nCommands:\n' % (prog,))
            maxlen = max(len(subcommand) for subcommand in subcommands) + 1
            for subcommand, (parser, main) in sorted(subcommands.iteritems()):
                doc = main.__doc__
                if doc is None:
                    sys.stderr.write('  %s\n' % (subcommand,))
                else:
                    doc = doc.split('\n', 1)[0]
                    sys.stderr.write('  %-*s %s\n' % (maxlen, subcommand, doc))
            sys.stderr.write(
                '\nUse --help after a subcommand for more help.\n')
            sys.exit(1)
    options = None
    option_parser = parser_class(prog=prog)
    try:
        options, args = option_parser.parse_args(args)
        # Checked here and not in OptionParser because we want our
        # check_values to run before the user's, not after it.
        if args:
            option_parser.error("I don't know what to do with %s" %
                                (' '.join(args),))
            # We should not get here, this is protection against
            # weird OptionParser subclasses.
            exitstatus = 1
        else:
            if options.nocolor:
                out = formatters.PlainTextFormatter(sys.stdout)
            else:
                out = formatters.get_formatter(sys.stdout)
            exitstatus = main_func(options, out, sys.stderr)
    except errors.ConfigurationError, e:
        if options is not None and options.debug:
            raise
        sys.stderr.write('Error in configuration:\n%s\n' % (e,))
        exitstatus = 1
    except (KeyboardInterrupt, formatters.StreamClosed):
        if options is not None and options.debug:
            raise
        exitstatus = 1
    if sys_exit:
        sys.exit(exitstatus)
    else:
        return exitstatus
