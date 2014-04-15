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

__all__ = ("FormattingHandler", "Values", "Option", "OptionParser",
    "MySystemExit", "main",
)

import sys
import os.path
import logging

from pkgcore.config import load_config, errors
from snakeoil import formatters, demandload, currying, modules
from snakeoil import compatibility
import optparse
from pkgcore.util import argparse
from pkgcore.util.commandline_optparse import *

demandload.demandload(globals(),
    'copy@_copy',
    'snakeoil:osutils',
    'snakeoil.errors:walk_exception_chain',
    'snakeoil.lists:iflatten_instance',
    'pkgcore:version@_version',
    'pkgcore.config:basics',
    'pkgcore.restrictions:packages,restriction',
    'pkgcore.util:parserestrict',
    'pkgcore:operations',
    'traceback',
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


CONFIG_ALL_DEFAULT = object()


class EnableDebug(argparse._StoreTrueAction):

    def __call__(self, parser, namespace, values, option_string=None):
        super(EnableDebug, self).__call__(parser, namespace, values,
            option_string=option_string)
        logging.root.setLevel(logging.DEBUG)


class ConfigError(Exception):
    pass


class NoDefaultConfigError(ConfigError):
    pass


class StoreConfigObject(argparse._StoreAction):

    default_priority = 20

    def __init__(self, *args, **kwargs):
        self.priority = int(kwargs.pop("priority", self.default_priority))
        self.config_type = kwargs.pop("config_type", None)
        if self.config_type is None or not isinstance(self.config_type, str):
            raise ValueError("config_type must specified, and be a string")

        if kwargs.pop("get_default", False):
            kwargs["default"] = DelayedValue(currying.partial(self.store_default,
                self.config_type, option_string=kwargs.get('option_strings', [None])[0]),
                self.priority)

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

    def _get_sections(self, config, namespace):
        return getattr(config, self.config_type)

    def _real_call(self, parser, namespace, values, option_string=None):
        config = getattr(namespace, 'config', None)
        if config is None:
            raise ValueError("no config found.  Internal bug")

        sections = self._get_sections(config, namespace)

        if self.nargs == argparse.ZERO_OR_MORE and values == []:
            values = sections.keys()

        if values is CONFIG_ALL_DEFAULT:
            value = [self._load_obj(sections, x) for x in sections]
        elif isinstance(values, basestring):
            value = self._load_obj(sections, values)
        else:
            value = [self._load_obj(sections, x) for x in values]
        setattr(namespace, self.dest, value)

    @staticmethod
    def store_default(config_type, namespace, attr, option_string=None):
        config = getattr(namespace, 'config', None)
        if config is None:
            raise ConfigError("no config found.  Internal bug, or broken on disk configuration.")
        obj = config.get_default(config_type)
        if obj is None:
            known_objs = sorted(getattr(config, config_type).keys())
            msg = "config error: no default object of type %r found.  " % (config_type,)
            if not option_string:
                msg += "Please fix your configuration."
            else:
                msg += "Please either fix your configuration, or set the %s " \
                    "via the %s option." % (config_type, option_string)
            if known_objs:
                msg += "Known %ss: %s" % (config_type, ', '.join(map(repr, known_objs)))
            raise NoDefaultConfigError(msg)
        setattr(namespace, attr, obj)

    @staticmethod
    def store_all_default(config_type, namespace, attr):
        config = getattr(namespace, 'config', None)
        if config is None:
            raise ValueError("no config found.  Internal bug")
        obj = [(k, v) for k, v in getattr(config, config_type).iteritems()]
        setattr(namespace, attr, obj)

    @classmethod
    def lazy_load_object(cls, config_type, key, priority=None):
        if priority is None:
            priority = cls.default_priority
        return DelayedValue(
            currying.partial(cls._lazy_load_object, config_type, key),
            priority)

    @staticmethod
    def _lazy_load_object(config_type, key, namespace, attr):
        try:
            obj = getattr(namespace.config, config_type)[key]
        except KeyError:
            raise ConfigError("Failed loading object %s of type %s"
                % (config_type, key))
            raise argparse.ArgumentError(self, "couldn't find %s %r" %
                (self.config_type, name))
        setattr(namespace, attr, obj)


class StoreRepoObject(StoreConfigObject):

    def __init__(self, *args, **kwargs):
        if 'config_type' in kwargs:
            raise ValueError("StoreRepoObject: config_type keyword is redundant: got %s"
                % (kwargs['config_type'],))
        self.raw = kwargs.pop("raw", False)
        self.domain_forced = 'domain' in kwargs
        self.domain = kwargs.pop('domain', 'domain')
        if self.raw:
            kwargs['config_type'] = 'raw_repo'
        else:
            kwargs['config_type'] = 'repo'
        self.allow_name_lookup = kwargs.pop("allow_name_lookup", True)
        StoreConfigObject.__init__(self, *args, **kwargs)

    def _get_sections(self, config, namespace):
        domain = None
        if self.domain:
            domain = getattr(namespace, self.domain, None)
            if domain is None and self.domain_forced:
                raise ConfigError(
                    "No domain found, but one was forced for %s; "
                    "internal bug.  NS=%s" % (self, namespace))
        if domain is None:
            return StoreConfigObject._get_sections(self, config, namespace)
        return domain.repos_raw if self.raw else domain.repos_configured_filtered

    def _load_obj(self, sections, name):
        if not self.allow_name_lookup or name in sections:
            return StoreConfigObject._load_obj(self, sections, name)

        # name wasn't found; search for it.
        for repo_name, repo in sections.iteritems():
            if name in repo.aliases.values():
                name = repo_name
                break

        return StoreConfigObject._load_obj(self, sections, name)


class DomainFromPath(StoreConfigObject):

    def __init__(self, *args, **kwargs):
        kwargs['config_type'] = 'domain'
        StoreConfigObject.__init__(self, *args, **kwargs)

    def _load_obj(self, sections, requested_path):
        targets = list(find_domains_from_path(sections, requested_path))
        if not targets:
            raise ValueError("couldn't find domain at path %r" % (requested_path,))
        elif len(targets) != 1:
            raise ValueError("multiple domains claim root %r: domains %s" %
                (requested_path, ', '.join(repr(x[0]) for x in targets)))
        return targets[0][1]


def find_domains_from_path(sections, path):
    path = osutils.normpath(osutils.abspath(path))
    for name, domain in sections.iteritems():
        root = getattr(domain, 'root', None)
        if root is None:
            continue
        root = osutils.normpath(osutils.abspath(root))
        if root == path:
            yield name, domain


class DelayedValue(object):

    def __init__(self, invokable, priority):
        self.priority = priority
        if not callable(invokable):
            raise TypeError("invokable must be callable")
        self.invokable = invokable

    def __call__(self, namespace, attr):
        self.invokable(namespace, attr)


class DelayedDefault(DelayedValue):

    @classmethod
    def wipe(cls, attrs, priority):
        if isinstance(attrs, basestring):
            attrs = (attrs,)
        return cls(currying.partial(cls._wipe, attrs), priority)

    @staticmethod
    def _wipe(attrs, namespace, triggering_attr):
        for attr in attrs:
            try:
                delattr(namespace, attr)
            except AttributeError:
                pass
        try:
            delattr(namespace, triggering_attr)
        except AttributeError:
            pass


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

    def __init__(self, attrs, klass_type=None, priority=100, converter=None):
        if klass_type == 'and':
            self.klass = packages.AndRestriction
        elif klass_type == 'or':
            self.klass = packages.OrRestriction
        elif callable(klass_type):
            self.klass = klass
        else:
            raise ValueError("klass_type either needs to be 'or', 'and', "
                "or a callable.  Got %r" % (klass_type,))

        if converter is not None and not callable(converter):
            raise ValueError("converter either needs to be None, or a callable;"
                " got %r" % (converter,))

        self.converter = converter
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

        l = list(iflatten_instance(l, (restriction.base,)))

        if self.converter:
            l = self.converter(l, namespace)
        if len(l) > 1:
            val = self.klass(*l)
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
    if kwargs.get('type', False) is None:
        del kwargs['type']
    else:
        kwargs.setdefault("type", parse_restriction)
    kwargs.setdefault("metavar", dest)
    final_priority  = kwargs.pop("final_priority", None)
    final_converter = kwargs.pop("final_converter", None)
    parser.add_argument(*args, **kwargs)
    bool_kwargs = {'converter':final_converter}
    if final_priority is not None:
        bool_kwargs['priority'] = final_priority
    obj = BooleanQuery(list(attrs) + [subattr], klass_type=klass_type, **bool_kwargs)
    # note that dict expansion has to be used here; dest=obj would just set a
    # default named 'dest'
    parser.set_defaults(**{dest:obj})


class Expansion(argparse.Action):

    def __init__(self, option_strings, dest, nargs=None, help=None,
                 required=None, subst=None):
        if subst is None:
            raise TypeError("resultant_string must be set")

        super(Expansion, self).__init__(option_strings=option_strings,
            dest=dest,
            help=help,
            required=required,
            default=False,
            nargs=nargs)
        self.subst = tuple(subst)

    def __call__(self, parser, namespace, values, option_string=None):
        actions = parser._actions
        action_map = {}
        vals = values
        if isinstance(values, basestring):
            vals = [vals]
        dvals = dict((str(idx), val) for (idx, val) in enumerate(vals))
        dvals['*'] = ' '.join(vals)

        for action in parser._actions:
            action_map.update((option, action) for option in action.option_strings)

        for chunk in self.subst:
            option, args = chunk[0], chunk[1:]
            action = action_map.get(option)
            args = [x % dvals for x in args]
            if not action:
                raise ValueError("unable to find option %r for %r" (option, self.option_strings))
            if action.type is not None:
                args = map(action.type, args)
            if action.nargs in (1, None):
                args = args[0]
            action(parser, namespace, args, option_string=option_string)
        setattr(namespace, self.dest, True)


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
        compatibility.raise_from(argparse.ArgumentTypeError(str(err)))


class VersionFunc(argparse.Action):

    def __init__(self, option_strings,
                 dest=argparse.SUPPRESS, default=argparse.SUPPRESS,
                 nargs=0,
                 version_func=None):
        super(VersionFunc, self).__init__(option_strings,
            dest=dest,
            default=default,
            nargs=nargs,
            help="show program's version number and exit")
        self.version_func = version_func

    def __call__(self, parser, namespace, values, option_string=None):
        formatter = parser._get_formatter()
        formatter.add_text(self.version_func())
        parser.exit(message=formatter.format_help())


class _SubParser(argparse._SubParsersAction):

    def add_parser(self, name, **kwds):
        """modified version of argparse._SubParsersAction, linking description/help if one is specified"""
        description = kwds.get("description")
        help_txt = kwds.get("help")
        if description is None:
            if help_txt is not None:
                kwds["description"] = help_txt
        elif help_txt is None:
            kwds["help"] = description
        return argparse._SubParsersAction.add_parser(self, name, **kwds)


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
        # register our own subparser
        self.register('action', 'parsers', _SubParser)

    def parse_args(self, args=None, namespace=None):
        args = argparse.ArgumentParser.parse_args(self, args, namespace)

        # two runs are required; first, handle any suppression defaults
        # introduced.  subparsers defaults cannot override the parent parser,
        # as such a subparser can't turn off config/domain for example.
        # so we first find all DelayedDefault
        # run them, then rescan for delayeds to run.
        # this allows subparsers to introduce a default named for themselves
        # that suppresses the parent.

        # intentionally no protection of suppression code; this should
        # just work.

        i = ((attr, val) for attr, val in args.__dict__.iteritems()
            if isinstance(val, DelayedDefault))
        for attr, functor in sorted(i, key=lambda val:val[1].priority):
            functor(args, attr)

        # now run the delays.
        i = ((attr, val) for attr, val in args.__dict__.iteritems()
            if isinstance(val, DelayedValue))
        try:
            for attr, delayed in sorted(i, key=lambda val:val[1].priority):
                delayed(args, attr)
        except (TypeError, ValueError), err:
            self.error("failed loading/parsing %s: %s" % (attr, str(err)))
        except (ConfigError, argparse.ArgumentError):
            err = sys.exc_info()[1]
            self.error(str(err))

        final_check = getattr(args, 'final_check', None)
        if final_check is not None:
            del args.final_check
            final_check(self, args)
        return args

    def bind_main_func(self, functor):
        self.set_defaults(main_func=functor)
        return functor

    def bind_class(self, obj):
        if not isinstance(obj, ArgparseCommand):
            raise ValueError("expected obj to be an instance of "
                "ArgparseCommand; got %r" % (obj,))
        obj.bind_to_parser(self)
        return self

    def bind_delayed_default(self, priority, name=None):
        def f(functor, name=name):
            if name is None:
                name = functor.__name__
            self.set_defaults(**{name:DelayedValue(functor, priority)})
            return functor
        return f

    def add_subparsers(self, **kwargs):
        kwargs.setdefault('title', 'subcommands')
        return argparse.ArgumentParser.add_subparsers(self, **kwargs)

    def bind_final_check(self, functor):
        self.set_defaults(final_check=functor)
        return functor


class ArgparseCommand(object):

    def bind_to_parser(self, parser):
        parser.bind_main_func(self)

    def __call__(self, namespace, out, err):
        raise NotImplementedError(self, '__call__')

def register_command(commands, real_type=type):
    def f(name, bases, scope, real_type=real_type, commands=commands):
        o = real_type(name, bases, scope)
        commands.append(o)
        return o
    return f

def _convert_config_mods(iterable):
    d = {}
    if iterable is None:
        return d
    for (section, key, value) in iterable:
        d.setdefault(section, {})[key] = value
    return d

def store_config(namespace, attr):
    configs = map(_convert_config_mods,
        [namespace.new_config, namespace.add_config])
    # add necessary inherits for add_config
    for key, vals in configs[1].iteritems():
        vals.setdefault('inherit', key)

    configs = [dict((section, basics.ConfigSectionFromStringDict(vals))
        for section, vals in d.iteritems())
            for d in configs if d]

    config = load_config(skip_config_files=namespace.empty_config,
        debug=getattr(namespace, 'debug', False),
        append_sources=tuple(configs))
    setattr(namespace, attr, config)


def _mk_domain(parser):
    parser.add_argument('--domain', get_default=True, config_type='domain',
        action=StoreConfigObject,
        help="domain to use for this operation")

def existent_path(value):
    if not os.path.exists(value):
        raise ValueError("path %r doesn't exist on disk" % (value,))
    try:
        return osutils.abspath(value)
    except EnvironmentError, e:
        compatibility.raise_from(
            ValueError("while resolving path %r, encountered error: %r" %
                (value, e)))

def mk_argparser(suppress=False, config=True, domain=True,
                 color=True, debug=True, version=True, **kwds):
    if isinstance(version, basestring):
        kwds["version"] = version
        version = None
    p = ArgumentParser(**kwds)
    p.register('action', 'extend_comma', ExtendCommaDelimited)

    if suppress:
        return p

    if version:
        if not callable(version):
            version = _version.get_version
        p.add_argument('--version', action=VersionFunc,
            version_func=version)
    if debug:
        p.add_argument('--debug', action=EnableDebug, help="Enable debugging checks")
    if color:
        p.add_argument('--color', action=StoreBool,
            default=True,
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
        _mk_domain(p)
    return p


def argparse_parse(parser, args, namespace=None):
    namespace = parser.parse_args(args, namespace=namespace)
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
        compatibility.raise_from(
            optparse.OptionValueError("arg %r isn't a valid atom: %s"
                % (x, e)))
    return l or [default]


def main(subcommands, args=None, outfile=None, errfile=None, script_name=None):
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

    out_fd = err_fd = None
    if hasattr(outfile, 'fileno') and hasattr(errfile, 'fileno'):
        if compatibility.is_py3k:
            # annoyingly, fileno can exist but through unsupport
            import io
            try:
                out_fd, err_fd = outfile.fileno(), errfile.fileno()
            except (io.UnsupportedOperation, IOError):
                pass
        else:
            try:
                out_fd, err_fd = outfile.fileno(), errfile.fileno()
            except IOError:
                # shouldn't be possible, but docs claim it, thus protect.
                pass

    if out_fd is not None and err_fd is not None:
        out_stat, err_stat = os.fstat(out_fd), os.fstat(err_fd)
        if out_stat.st_dev == err_stat.st_dev \
            and out_stat.st_ino == err_stat.st_ino and \
            not errfile.isatty():
            # they're the same underlying fd.  thus
            # point the handles at the same so we don't
            # get intermixed buffering issues.
            errfile = outfile

    out = options = None
    exitstatus = -10
    try:
        if isinstance(subcommands, dict):
            main_func, options = optparse_parse(subcommands, args=args, script_name=script_name,
                errfile=errfile)
        else:
            options = argparse.Namespace()
            main_func, options = argparse_parse(subcommands, args, options)

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
    except KeyboardInterrupt:
        if getattr(options, 'debug', False):
            raise
        errfile.write("keyboard interupted- exiting\n")
        exitstatus = 1
    except compatibility.IGNORED_EXCEPTIONS:
        raise
    except errors.ConfigurationError, e:
        tb = sys.exc_info()[-1]
        if not getattr(options, 'debug', False):
            tb = None
        dump_error(errfile, e, "Error in configuration", tb=tb)
    except operations.OperationError, e:
        tb = sys.exc_info()[-1]
        if not getattr(options, 'debug', False):
            tb = None
        dump_error(errfile, e, "Error running an operation", tb=tb)
    except Exception, e:
        tb = sys.exc_info()[-1]
        if not getattr(options, 'debug', False):
            tb = None
        dump_error(errfile, e, "Unhandled Exception occurred", tb=tb)
    if out is not None:
        if exitstatus:
            out.title('%s failed' % (options.prog,))
        else:
            out.title('%s succeeded' % (options.prog,))
    raise MySystemExit(exitstatus)

def dump_error(handle, raw_exc, context_msg=None, tb=None):
    prefix = ''
    if context_msg:
        prefix = ' '
        handle.write(context_msg.rstrip("\n") + ":\n")
        if tb:
            handle.write("Traceback follows:\n")
            traceback.print_tb(tb, file=handle)
            handle.write("\nError was:\n")
    exc_strings = []
    if raw_exc is not None:
        for exc in walk_exception_chain(raw_exc):
            exc_strings.extend('%s%s' % (prefix, x.strip())
                for x in filter(None, str(exc).split("\n")))
    if exc_strings:
        handle.write("\n".join(exc_strings))
        handle.write("\n")
