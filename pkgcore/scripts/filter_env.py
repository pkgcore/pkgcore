# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Commandline interface to L{pkgcore.ebuild.filter_env}."""


import sys

from pkgcore.util import commandline
# ordering here matters; commandline does a trick to copy to avoid the heavy inspect load.
import optparse
from pkgcore.ebuild import filter_env
from pkgcore.log import logger


def input_callback(option, opt_str, value, parser):
    if parser.values.input is not None:
        raise optparse.OptionValueError('-i cannot be specified twice')
    try:
        parser.values.input = open(value, 'r')
    except (IOError, OSError), e:
        raise optparse.OptionValueError('error opening %r (%s)' % (value, e))


def append_comma_separated(option, opt_str, value, parser):
    parser.values.ensure_value(option.dest, []).extend(
        v for v in value.split(',') if v)


class OptionParser(commandline.OptionParser):

    def _register_options(self):
        self.add_option(
            '-V', '--var-match', action='store_false', default=True)
        self.add_option(
            '-F', '--func-match', action='store_false', default=True)
        self.add_option(
            '--input', '-i', action='callback', type='string',
            callback=input_callback,
            help='Filename to read the env from (uses stdin if omitted).')
        self.add_option(
            '--funcs', '-f', action='callback', type='string',
            callback=append_comma_separated)
        self.add_option(
            '--vars', '-v', action='callback', type='string',
            callback=append_comma_separated)
        self.add_option(
            '--print-vars', action='store_true', default=False,
            help="print just the global scope environment variables that match")

    def _check_values(self, values, args):
        if values.input is None:
            # Hack: use stdin if it is not a tty. No util.commandline
            # support for this kind of thing, so mess around with sys
            # directly.
            if sys.stdin.isatty():
                self.error('No input file supplied (and stdin is a tty).')
            values.input = sys.stdin

        return values, args


def main(options, out, err):
    if options.debug:
        if options.funcs is None:
            logger.debug('=== Funcs: None')
        else:
            logger.debug('=== Funcs:')
            for thing in options.funcs:
                logger.debug(repr(thing))
        if options.vars is None:
            logger.debug('=== Vars: None')
        else:
            logger.debug('=== Vars:')
            for thing in options.vars:
                logger.debug(repr(thing))
        logger.debug('var_match: %r, func_match: %r',
                     options.var_match, options.func_match)

    if options.funcs:
        funcs = filter_env.build_regex_string(options.funcs)
    else:
        funcs = None

    if options.vars:
        vars = filter_env.build_regex_string(options.vars)
    else:
        vars = None

    file_buff = options.input.read() + '\0'

    stream = out.stream
    var_callback = None
    if options.print_vars:
        import cStringIO
        stream = cStringIO.StringIO()
        var_matches = []
        var_callback = var_matches.append

    # Hack: write to the stream directly.
    filter_env.run(stream, file_buff, vars, funcs,
                   options.var_match, options.func_match,
                   global_envvar_callback=var_callback)

    if options.print_vars:
        for var in sorted(var_matches):
            out.write(var.strip())
