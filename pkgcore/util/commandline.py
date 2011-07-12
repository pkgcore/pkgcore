# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Utilities for writing commandline utilities.

pkgcore scripts should use the L{OptionParser} subclass here for a
consistent commandline "look and feel" (and it tries to make life a
bit easier too). They will probably want to use L{main} from an C{if
__name__ == '__main__'} block too: it will take care of things like
consistent exception handling.

See dev-notes/commandline.rst for more complete documentation.
"""

__all__ = ("FormattingHandler", "Values", "Option", "OptionParser",
    "MySystemExit", "main",
)

import sys
import os.path
import logging

from pkgcore.config import load_config, errors
from snakeoil import formatters, demandload, currying, modules
import optparse
from pkgcore.util import argparse
from pkgcore.util.commandline_optparse import *

demandload.demandload(globals(),
    'copy@_copy',
    'snakeoil.fileutils:iter_read_bash',
    'snakeoil:osutils',
    'pkgcore:version',
    'pkgcore.config:basics',
    'pkgcore.restrictions:packages,restriction',
    'pkgcore.util:parserestrict',
    'pkgcore.ebuild:atom',
)


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


def string_bool(value):
    value = value.lower()
    if value in ('y', 'yes', 'true'):
        return True
    elif value in ('n', 'no', 'false'):
        return False
    raise ValueError(value)


class ExtendCommaDelimited(argparse._AppendAction):

    def __call__(self, parser, namespace, values, option_string=None):
        items = _copy.copy(argparse._ensure_value(namespace, self.dest, []))
        if not self.nargs or self.nargs < 1:
            items.extend(filter(None, values.split(',')))
        else:
            for value in values:
                items.extend(filter(None, value.split(',')))
        setattr(namespace, self.dest, items)


class StoreBool(argparse._StoreAction):
    def __init__(self,
                option_strings,
                dest,
                const=None,
                default=None,
                required=False,
                help=None,
                metavar='BOOLEAN'):
        super(StoreBool, self).__init__(
            option_strings=option_strings,
            dest=dest,
            const=const,
            default=default,
            type=self.convert_bool,
            required=required,
            help=help,
            metavar=metavar)

    @staticmethod
    def convert_bool(value):
        value = value.lower()
        if value in ('y', 'yes', 'true'):
            return True
        elif value in ('n', 'no', 'false'):
            return False
        raise ValueError("value %r must be [y|yes|true|n|no|false]" % (value,))


class Delayed(argparse.Action):

    def __init__(self, option_strings, dest, target=None, priority=0, **kwds):
        if target is None:
            raise ValueError("target must be non None for Delayed")

        self.priority = int(priority)
        self.target = target(option_strings=option_strings, dest=dest, **kwds.copy())
        super(Delayed, self).__init__(option_strings=option_strings[:],
            dest=dest, nargs=kwds.get("nargs", None), required=kwds.get("required", None),
            help=kwds.get("help", None), metavar=kwds.get("metavar", None))

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, DelayedParse(
            currying.partial(self.target, parser, namespace, values, option_string),
            self.priority))


class StoreConfigObject(argparse._StoreAction):

    default_priority = 20

    def __init__(self,
                *args,
                **kwargs):

        self.priority = int(kwargs.pop("priority", self.default_priority))
        self.config_type = kwargs.pop("config_type", None)
        if self.config_type is None or not isinstance(self.config_type, str):
            raise ValueError("config_type must specified, and be a string")

        if kwargs.pop("get_default", False):
            kwargs["default"] = DelayedValue(currying.partial(self.store_default,
                self.config_type), self.priority)

        self.store_name = kwargs.pop("store_name", False)
        self.writable = kwargs.pop("writable", None)
        self.target = argparse._StoreAction(*args, **kwargs)

        super(StoreConfigObject, self).__init__(*args, **kwargs)

    def _load_obj(self, sections, name):
        try:
            val = sections[name]
        except KeyError:
            raise argparse.ArgumentError(self, "couldn't find %s %r" %
                (self.config_type, name))

        if self.writable and getattr(val, 'frozen', False):
            raise argparse.ArgumentError(self, "%s %r is readonly" %
                (self.config_type, name))

        if self.store_name:
            return name, val
        return val

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, DelayedParse(
            currying.partial(self._real_call, parser, namespace, values, option_string),
            self.priority))

    def _real_call(self, parser, namespace, values, option_string=None):
        config = getattr(namespace, 'config', None)
        if config is None:
            raise ValueError("no config found.  Internal bug")

        sections = getattr(config, self.config_type)
        if isinstance(values, basestring):
            value = self._load_obj(sections, values)
        else:
            value = [self._load_obj(sections, x) for x in values]
        setattr(namespace, self.dest, value)

    @staticmethod
    def store_default(config_type, namespace, attr):
        config = getattr(namespace, 'config', None)
        if config is None:
            raise ValueError("no config found.  Internal bug")
        obj = config.get_default(config_type)
        if obj is None:
            raise ValueError("config error: no default object of type %r found" % (config_type,))
        setattr(namespace, attr, obj)


class DelayedValue(object):

    def __init__(self, invokable, priority):
        self.priority = priority
        if not callable(invokable):
            raise TypeError("invokable must be callable")
        self.invokable = invokable

    def __call__(self, namespace, attr):
        self.invokable(namespace, attr)


class DelayedParse(DelayedValue):

    def __init__(self, invokable, priority):
        DelayedValue.__init__(self, invokable, priority)

    def __call__(self, namespace, attr):
        self.invokable()


def parse_restriction(value):
    # this should be eliminated, and directly accessing the actual function.
    # note it throws ValueErrors...
    return parserestrict.parse_match(value)


class BooleanQuery(DelayedValue):

    def __init__(self, attrs, klass_type=None, priority=100):
        if klass_type == 'and':
            self.klass = packages.AndRestriction
        elif klass_type == 'or':
            self.klass = packages.OrRestriction
        elif callable(klass_type):
            self.klass = klass
        else:
            raise ValueError("klass_type either needs to be 'or', 'and', "
                "or a callable.  Got %r" % (klass_type,))

        self.priority = int(priority)
        self.attrs = tuple(attrs)

    def invokable(self, namespace, attr):
        l = []
        for x in self.attrs:
            val = getattr(namespace, x, None)
            if val is None:
                continue
            if isinstance(val, restriction.base):
                l.append(val)
            else:
                l.extend(val)
        if len(l) > 1:
            val = self.klass(*val)
        elif l:
            val = l[0]
        else:
            val = None
        setattr(namespace, attr, val)


def make_query(parser, *args, **kwargs):
    klass_type = kwargs.pop("klass_type", "or")
    dest = kwargs.pop("dest", None)
    if dest is None:
        raise TypeError("dest must be specified via kwargs")
    attrs = kwargs.pop("attrs", [])
    subattr = "_%s" % (dest,)
    kwargs["dest"] = subattr
    kwargs.setdefault("type", parse_restriction)
    kwargs.setdefault("metavar", dest)
    parser.add_argument(*args, **kwargs)
    kwargs2 = {}
    kwargs2[dest] = BooleanQuery(list(attrs) + [subattr], klass_type=klass_type)
    parser.set_defaults(**kwargs2)


def python_namespace_type(value, module=False, attribute=False):
    """
    return the object from python namespace that value specifies

    :param value: python namespace, snakeoil.modules for example
    :param module: if true, the object must be a module
    :param attribute: if true, the object must be a non-module
    :raises ValueError: if the conditions aren't met, or import fails
    """
    try:
        if module:
            return modules.load_module(value)
        elif attribute:
            return modules.load_attribute(value)
        return modules.load_any(value)
    except modules.FailedImport, err:
        raise argparse.ArgumentTypeError(str(err))


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self,
                 prog=None,
                 usage=None,
                 description=None,
                 epilog=None,
                 version=None,
                 parents=[],
                 formatter_class=argparse.HelpFormatter,
                 prefix_chars='-',
                 fromfile_prefix_chars=None,
                 argument_default=None,
                 conflict_handler='error',
                 add_help=True):
        super(ArgumentParser, self).__init__(prog=prog, usage=usage,
            description=description, epilog=epilog, version=version,
            parents=parents, formatter_class=formatter_class,
            prefix_chars=prefix_chars, fromfile_prefix_chars=fromfile_prefix_chars,
            argument_default=argument_default, conflict_handler=conflict_handler,
            add_help=add_help)

    def parse_args(self, args=None, namespace=None):
        args = argparse.ArgumentParser.parse_args(self, args, namespace)

        # bleh.  direct access...
        i = ((attr, val) for attr, val in args.__dict__.iteritems()
            if isinstance(val, DelayedValue))
        try:
            for attr, delayed in sorted(i, key=lambda val:val[1].priority):
                delayed(args, attr)
        except (TypeError, ValueError), err:
            self.error("failed loading/parsing %s: %s" % (attr, str(err)))
        except argparse.ArgumentError:
            err = sys.exc_info()[1]
            self.error(str(err))

        return args

    def bind_main_func(self, functor):
        self.set_defaults(main_func=functor)
        return functor

def _convert_config_mods(iterable):
    d = {}
    if iterable is None:
        return d
    for (section, key, value) in iterable:
        d.setdefault(section, {})[key] = value
    return d

def store_config(namespace, attr):
    prepend = map(_convert_config_mods,
        [namespace.new_config, namespace.add_config])
    # add necessary inherits for add_config
    for key, vals in prepend[1].iteritems():
        vals.setdefault('inherit', key)

    prepend = [dict((section, basics.ConfigSectionFromStringDict(vals))
        for section, vals in d.iteritems())
            for d in prepend if d]

    config = load_config(skip_config_files=namespace.empty_config,
        debug=getattr(namespace, 'debug', False),
        prepend_sources=tuple(prepend))
    setattr(namespace, attr, config)


def mk_argparser(suppress=False, config=True, domain=True, color=True, debug=True, **kwds):
    p = ArgumentParser(**kwds)
    if suppress:
        return p
    if debug:
        p.add_argument('--debug', action='store_true', help="Enable debugging checks")
    if color:
        p.add_argument('--color', action=StoreBool,
            help="Enable or disable color support.")

    if config:
        p.add_argument('--add-config', nargs=3, action='append',
            metavar=("SECTION", "KEY", "VALUE"),
            help="modify an existing configuration section.")
        p.add_argument('--new-config', nargs=3, action='append',
            metavar=("SECTION", "KEY", "VALUE"),
            help="add a new configuration section.")
        p.add_argument('--empty-config', '--config-empty', action='store_true',
            default=False, dest='empty_config',
            help="Do not load user/system configuration.")

        p.set_defaults(config=DelayedValue(store_config, 0))

    if domain:
        p.add_argument('--domain', get_default=True, config_type='domain',
            action=StoreConfigObject,
            help="domain to use for this operation")
    return p


def argparse_parse(parser, args):
    namespace = parser.parse_args(args)
    main = getattr(namespace, 'main_func', None)
    if main is None:
        raise Exception("parser %r lacks a main method- internal bug.\nGot namespace %r\n"
            % (parser, namespace))
    namespace.prog = parser.prog
    return main, namespace

def convert_to_restrict(sequence, default=packages.AlwaysTrue):
    """Convert an iterable to a list of atoms, or return the default"""
    l = []
    try:
        for x in sequence:
            l.append(parserestrict.parse_match(x))
    except parserestrict.ParseError, e:
        raise optparse.OptionValueError("arg %r isn't a valid atom: %s"
            % (x, e))
    return l or [default]

def find_domains_from_path(config, path):
    path = osutils.normpath(osutils.abspath(path))
    for name, domain in config.domain.iteritems():
        root = getattr(domain, 'root', None)
        if root is None:
            continue
        root = osutils.normpath(osutils.abspath(root))
        if root == path:
            yield name, domain

def main(subcommands, args=None, outfile=None, errfile=None,
    script_name=None):
    """Function to use in an "if __name__ == '__main__'" block in a script.

    Takes one or more combinations of option parser and main func and
    runs them, taking care of exception handling and some other things.

    Any ConfigurationErrors raised from your function (by the config
    manager) are handled. Other exceptions are not (trigger a traceback).

    :type subcommands: mapping of string => (OptionParser class, main func)
    :param subcommands: available commands.
        The keys are a subcommand name or None for other/unknown/no subcommand.
        The values are tuples of OptionParser subclasses and functions called
        as main_func(config, out, err) with a L{Values} instance, two
        L{snakeoil.formatters.Formatter} instances for output (stdout)
        and errors (stderr). It should return an integer used as
        exit status or None as synonym for 0.
    :type args: sequence of strings
    :param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    :type outfile: file-like object
    :param outfile: File to use for stdout, defaults to C{sys.stdout}.
    :type errfile: file-like object
    :param errfile: File to use for stderr, defaults to C{sys.stderr}.
    :type script_name: string
    :param script_name: basename of this script, defaults to the basename
        of C{sys.argv[0]}.
    """
    exitstatus = 1

    if outfile is None:
        outfile = sys.stdout
    if errfile is None:
        errfile = sys.stderr

    options = out = None
    try:
        if isinstance(subcommands, dict):
            main_func, options = optparse_parse(subcommands, args=args, script_name=script_name,
                errfile=errfile)
        else:
            main_func, options = argparse_parse(subcommands, args)

        if getattr(options, 'color', True):
            formatter_factory = formatters.get_formatter
        else:
            formatter_factory = formatters.PlainTextFormatter
        out = formatter_factory(outfile)
        err = formatter_factory(errfile)
        if logging.root.handlers:
            # Remove the default handler.
            logging.root.handlers.pop(0)
        logging.root.addHandler(FormattingHandler(err))
        exitstatus = main_func(options, out, err)
    except errors.ConfigurationError, e:
        if getattr(options, 'debug', False):
            raise
        errfile.write('Error in configuration:\n%s\n' % (e,))
    except KeyboardInterrupt:
        if getattr(options, 'debug', False):
            raise
    if out is not None:
        if exitstatus:
            out.title('%s failed' % (options.prog,))
        else:
            out.title('%s succeeded' % (options.prog,))
    raise MySystemExit(exitstatus)
