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

    def parse(self, *args, **kwargs):
        """Parse a commandline and return the Values object.

        args are passed to parse_args, keyword args are used as config keys.
        """
        values = self.parser.get_default_values()
        values._config = central.ConfigManager([kwargs], debug=True)
        # optparse needs a list (it does make a copy, but it uses [:]
        # to do it, which is a noop on a tuple).
        options, args = self.parser.parse_args(list(args), values)
        self.assertFalse(args)
        return options

    def assertError(self, message, *args, **kwargs):
        """Pass args to the option parser and assert it errors message."""
        try:
            self.parse(*args, **kwargs)
        except Error, e:
            self.assertEqual(message, e.msg)
        else:
            self.fail('no error triggered')

    def assertExit(self, status, message, *args, **kwargs):
        """Pass args, assert they trigger the right exit condition."""
        try:
            self.parse(*args, **kwargs)
        except Exit, e:
            self.assertEqual(message, e.msg)
            self.assertEqual(status, e.status)
        else:
            self.fail('no exit triggered')

    def assertOut(self, out, *args, **kwargs):
        """Like L{assertOutAndErr} but without err."""
        return self.assertOutAndErr(out, (), *args, **kwargs)

    def assertErr(self, err, *args, **kwargs):
        """Like L{assertOutAndErr} but without out."""
        return self.assertOutAndErr((), err, *args, **kwargs)

    def assertOutAndErr(self, out, err, *args, **kwargs):
        """Parse options and run main.

        Extra arguments are parsed by the option parser.
        Keyword arguments are config sections.

        @param out: list of strings produced as output on stdout.
        @param err: list of strings produced as output on stderr.
        @return: the L{central.ConfigManager}.
        """
        options = self.parse(*args, **kwargs)
        outstream = StringIO.StringIO()
        errstream = StringIO.StringIO()
        outformatter = formatters.PlainTextFormatter(outstream)
        errformatter = formatters.PlainTextFormatter(errstream)
        self.main(options, outformatter, errformatter)
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
        return options.config
