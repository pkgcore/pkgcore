# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Helpers for testing scripts."""


import StringIO
import difflib

from pkgcore.util import formatters
from pkgcore.config import central


class Exit(Exception):

    """Used to catch parser.exit."""

    def __init__(self, status, msg):
        Exception.__init__(self, msg)
        self.status = status
        self.msg = msg

class Error(Exception):

    """Used to catch parser.error."""

    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg


def noexit(status=0, msg=None):
    raise Exit(status, msg)

def noerror(msg=None):
    raise Error(msg)

def mangle_parser(parser):
    """Make an OptionParser testable."""
    parser.exit = noexit
    parser.error = noerror
    return parser


class MainMixin(object):

    """Provide some utility methods for testing the parser and main.

    @cvar parser: OptionParser subclass to test.
    @cvar main: main function to test.
    """

    def assertError(self, message, *args):
        """Pass args to the option parser and assert it errors message."""
        try:
            # optparse wants to manipulate the args.
            self.parser.parse_args(list(args))
        except Error, e:
            self.assertEqual(message, e.msg)
        else:
            self.fail('no error triggered')

    def assertExit(self, status, message, *args):
        """Pass args, assert they trigger the right exit condition."""
        try:
            # optparse wants to manipulate the args.
            self.parser.parse_args(list(args))
        except Exit, e:
            self.assertEqual(message, e.msg)
            self.assertEqual(status, e.status)
        else:
            self.fail('no exit triggered')

    def assertOut(self, out, config, *args):
        """Like L{assertOutAndErr} but without err."""
        self.assertOutAndErr(out, (), config, *args)

    def assertErr(self, err, config, *args):
        """Like L{assertOutAndErr} but without out."""
        self.assertOutAndErr((), err, config, *args)

    def assertOutAndErr(self, out, err, config, *args):
        config = central.ConfigManager([config])
        options, args = self.parser.parse_args(list(args))
        self.assertFalse(args)
        outstream = StringIO.StringIO()
        errstream = StringIO.StringIO()
        outformatter = formatters.PlainTextFormatter(outstream)
        self.main(config, options, outformatter, errstream)
        diffs = []
        for name, strings, stream in [('out', out, outstream),
                                      ('err', err, errstream)]:
            actual = stream.getvalue()
            if strings:
                expected = '\n'.join(strings) + '\n'
            else:
                expected = ''
            if expected != actual:
                diffs.extend(difflib.unified_diff(
                        strings, actual.split('\n')[:-1],
                        'expected %s' % (name,), 'actual', lineterm=''))
        if diffs:
            self.fail('\n' + '\n'.join(diffs))
