# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Utilities for writing commandline utilities."""


import sys
import optparse

from pkgcore.config import load_config, errors

from pkgcore.util import formatters


class OptionParser(optparse.OptionParser):

    """Our common OptionParser subclass.

    Currently mostly empty, just adds some common options. Will
    probably grow though.
    """

    standard_option_list = optparse.OptionParser.standard_option_list + [
        optparse.Option('--debug', '-d', action='store_true',
                        help='print some extra info useful for pkgcore devs.'),
        optparse.Option('--nocolor', action='store_true',
                        help='disable color in the output.'),
        ]

    def check_values(self, vals, args):
        """Do some basic sanity checking."""
        # optparse defaults unset lists to None. An empty sequence is
        # much more convenient (lets you use them in a for loop
        # without a None check) so fix those up:
        for container in self.option_groups + [self]:
            for option in container.option_list:
                if option.action == 'append':
                    vals.ensure_value(option.dest, [])
        return vals, args


def main(option_parser, main_func, args=None, sys_exit=True):
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

    @type  option_parser: instance of L{OptionParser} (or a subclass).
    @param option_parser: option parser used to parse sys.argv.
    @type  main_func: callable, main_func(config, options, out, err)
    @param main_func: function called after the options are parsed and config
        is loaded. Arguments are the result of load_config(),
        an optparse.Values instance, a L{pkgcore.util.formatters.Formatter}
        for output and a filelike for errors (C{sys.stderr}). It should return
        an integer used as exit status or None as synonym for 0.
    @type  args: sequence of strings
    @param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    @type  sys_exit: boolean
    @param sys_exit: if True C{sys.exit} is called when done, otherwise
        the exitstatus is returned.
    """
    reraise_keyboard_interrupt = False
    try:
        options, args = option_parser.parse_args(args)
        reraise_keyboard_interrupt = options.debug
        # Checked here and not in OptionParser because we want our
        # check_values to run before the user's, not after it (may do
        # stuff there at some point).
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
            try:
                # Yes, we really want main() inside this block (to catch
                # delayed InstantiationErrors)
                exitstatus = main_func(load_config(debug=options.debug),
                                       options, out, sys.stderr)
            except errors.ConfigurationError, e:
                if options.debug:
                    raise
                sys.stderr.write('Error in configuration:\n%s\n' % (e,))
                exitstatus = 1
    except (KeyboardInterrupt, formatters.StreamClosed):
        if reraise_keyboard_interrupt:
            raise
        exitstatus = 1
    if sys_exit:
        sys.exit(exitstatus)
    else:
        return exitstatus
