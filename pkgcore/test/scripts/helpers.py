# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Helpers for testing scripts."""

import difflib, copy
from snakeoil.formatters import PlainTextFormatter
from snakeoil.caching import WeakInstMeta
from pkgcore.config import central, basics, ConfigHint
from pkgcore.util import commandline


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
    """Make an OptionParser or argparser testable."""
    # copy it.  avoid the potential of inadvertantly tainting what we're working on.
    parser = copy.copy(parser)
    parser.exit = noexit
    parser.error = noerror
    return parser


class fake_domain(object):
    pkgcore_config_type = ConfigHint(typename='domain')
    def __init__(self):
        pass

default_domain = basics.HardCodedConfigSection({
    'class': fake_domain,
    'default': True,
    })


class FormatterObject(object):
    __metaclass__ = WeakInstMeta
    __inst_caching__ = True
    def __call__(self, formatter):
        formatter.stream.write(self)

class Color(FormatterObject):
    __inst_caching__ = True
    def __init__(self, mode, color):
        self.mode = mode
        self.color = color
    def __repr__(self):
        return '<Color: mode - %s; color - %s>' % (self.mode, self.color)

class Reset(FormatterObject):
    __inst_caching__ = True
    def __repr__(self):
        return '<Reset>'

class Bold(FormatterObject):
    __inst_caching__ = True
    def __repr__(self):
        return '<Bold>'

class ListStream(list):
    def write(self, *args):
        stringlist = []
        objectlist = []
        for arg in args:
            if isinstance(arg, basestring):
                stringlist.append(arg)
            else:
                objectlist.append(''.join(stringlist))
                stringlist = []
                objectlist.append(arg)
        objectlist.append(''.join(stringlist))
        # We use len because boolean ops shortcircuit
        if (len(self) and isinstance(self[-1], basestring) and
                isinstance(objectlist[0], basestring)):
            self[-1] = self[-1] + objectlist.pop(0)
        self.extend(objectlist)

class FakeStreamFormatter(PlainTextFormatter):
    def __init__(self):
        PlainTextFormatter.__init__(self, ListStream([]))
        self.reset = Reset()
        self.bold = Bold()
        self.first_prefix = [None]
    def resetstream(self):
        self.stream = ListStream([])
    def fg(self, color=None):
        return Color('fg', color)
    def bg(self, color=None):
        return Color('bg', color)
    def get_text_stream(self):
        return ''.join([x for x in self.stream if not isinstance(x, FormatterObject)])

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

    def get_main(self, options):
        return self.main

    def assertOutAndErr(self, out, err, *args, **kwargs):
        """Parse options and run main.

        Extra arguments are parsed by the option parser.
        Keyword arguments are config sections.

        :param out: list of strings produced as output on stdout.
        :param err: list of strings produced as output on stderr.
        :return: the L{central.ConfigManager}.
        """
        options = self.parse(*args, **kwargs)
        outformatter = FakeStreamFormatter()
        errformatter = FakeStreamFormatter()
        main = self.get_main(options)
        main(options, outformatter, errformatter)
        diffs = []
        for name, strings, formatter in [('out', out, outformatter),
                                         ('err', err, errformatter)]:
            actual = formatter.get_text_stream()
            if strings:
                expected = '\n'.join(strings)
            else:
                expected = ''
            if expected != actual:
                diffs.extend(difflib.unified_diff(
                        strings, actual.split('\n')[:-1],
                        'expected %s' % (name,), 'actual', lineterm=''))
        if diffs:
            self.fail('\n' + '\n'.join(diffs))
        return options.config


class ArgParseMixin(MainMixin):

    suppress_domain = False

    def parse(self, *args, **kwargs):
        """Parse a commandline and return the Values object.

        args are passed to parse_args, keyword args are used as config keys.
        """
        namespace = commandline.argparse.Namespace()
        if kwargs.pop("suppress_domain", self.suppress_domain):
            kwargs["default_domain"] = default_domain
        namespace.config = central.ConfigManager([kwargs], debug=True)
        # optparse needs a list (it does make a copy, but it uses [:]
        # to do it, which is a noop on a tuple).
        namespace = self.parser.parse_args(list(args), namespace=namespace)
        return namespace

    @property
    def parser(self):
        p = copy.copy(self._argparser)
        return mangle_parser(p)

    def get_main(self, namespace):
        return namespace.main_func
