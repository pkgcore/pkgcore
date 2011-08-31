# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Commandline interface to :obj:`pkgcore.ebuild.filter_env`."""

__all__ = ("argparser", "main")

import sys

from pkgcore.util import commandline
# ordering here matters; commandline does a trick to copy to avoid the heavy inspect load.
from pkgcore.ebuild import filter_env
from pkgcore.log import logger

argparser = commandline.mk_argparser(config=False, domain=False, color=False)
argparser.add_argument('-V', '--var-match', action='store_true',
    default=False,
    help="Invert the filtering- instead of removing a var if it matches "
    "remove all vars that do not match")
argparser.add_argument('-F', '--func-match', action='store_true',
    default=False,
    help="Invert the filtering- instead of removing a function if it matches "
    "remove all functions that do not match")

def stdin_default(namespace, attr):
    if sys.stdin.isatty():
        raise ValueError("Refusing to read from stdin since it's a TTY")
    setattr(namespace, attr, sys.stdin)

argparser.add_argument('--input', '-i', action='store',
    type=commandline.argparse.FileType(), default=commandline.DelayedValue(stdin_default, 0),
    help='Filename to read the env from (uses stdin if omitted).')
argparser.add_argument('--funcs', '-f', action=commandline.ExtendCommaDelimited,
    help="commad seperated list of regexes to match function names against for filtering")
argparser.add_argument('--vars', '-v', action=commandline.ExtendCommaDelimited,
    help="commad seperated list of regexes to match variable names against for filtering")
argparser.add_argument('--print-vars', action='store_true', default=False,
    help="print just the global scope environment variables that match")

@argparser.bind_main_func
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

    stream = out.stream
    var_callback = None
    if options.print_vars:
        import cStringIO
        stream = cStringIO.StringIO()
        var_matches = []
        var_callback = var_matches.append

    # Hack: write to the stream directly.
    filter_env.main_run(stream, options.input.read(), options.vars, options.funcs,
                   options.var_match, options.func_match,
                   global_envvar_callback=var_callback)

    if options.print_vars:
        for var in sorted(var_matches):
            out.write(var.strip())
