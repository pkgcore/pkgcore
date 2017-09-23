# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Utilities for writing commandline utilities.

pkgcore scripts should use the :obj:`ArgumentParser` subclass here for a
consistent commandline "look and feel" (and it tries to make life a
bit easier too). They will probably want to use :obj:`main` from an C{if
__name__ == '__main__'} block too: it will take care of things like
consistent exception handling.

See dev-notes/commandline.rst for more complete documentation.
"""

__all__ = (
    "Tool", "main",
)

import argparse
from functools import partial
from importlib import import_module
import os
import sys

from snakeoil import compatibility, modules
from snakeoil.cli import arghparse
from snakeoil.cli.tool import Tool as BaseTool
from snakeoil.demandload import demandload

from pkgcore.config import load_config, errors

demandload(
    'signal',
    'traceback',
    'snakeoil:osutils',
    'snakeoil.errors:dump_error,walk_exception_chain',
    'snakeoil.sequences:iflatten_instance,unstable_unique',
    'pkgcore:operations',
    'pkgcore.config:basics',
    'pkgcore.plugin:get_plugins',
    'pkgcore.restrictions:packages,restriction',
    'pkgcore.util:parserestrict',
)


class StoreTarget(argparse._AppendAction):
    """Parse extended package atom syntax and optionally set arguments.

    Various target arguments are supported including the following:

    atom
        An extended atom syntax is supported, see the related section
        in pkgcore(5).

    package set
        Used to define lists of packages, the syntax used for these is
        @pkgset. For example, the @system and @world package sets are
        supported.

    extended globbing
        Globbing package names or atoms allows for use cases such as
        ``'far*'`` (merge every package starting with 'far'),
        ``'dev-python/*::gentoo'`` (merge every package in the dev-python
        category from the gentoo repo), or even '*' (merge everything).

    Also, the target '-' allows targets to be read from standard input.
    """

    def __init__(self, sets=True, *args, **kwargs):
        super(StoreTarget, self).__init__(*args, **kwargs)
        self.sets = sets

    def __call__(self, parser, namespace, values, option_string=None):
        if self.sets:
            namespace.sets = []

        if isinstance(values, basestring):
            values = [values]
        elif values is not None and len(values) == 1 and values[0] == '-':
            if not sys.stdin.isatty():
                values = [x.strip() for x in sys.stdin.readlines() if x.strip() != '']
                # reassign stdin to allow interactivity (currently only works for unix)
                sys.stdin = open('/dev/tty')
            else:
                raise argparse.ArgumentError(self, "'-' is only valid when piping data in")

        for token in values:
            if self.sets and token.startswith('@'):
                namespace.sets.append(token[1:])
            else:
                try:
                    argparse._AppendAction.__call__(
                        self, parser, namespace,
                        (token, parserestrict.parse_match(token)), option_string=option_string)
                except parserestrict.ParseError as e:
                    parser.error(e)
        if getattr(namespace, self.dest) is None:
            setattr(namespace, self.dest, [])


CONFIG_ALL_DEFAULT = object()


class NoDefaultConfigError(argparse.ArgumentError):
    pass


class StoreConfigObject(argparse._StoreAction):

    default_priority = 20

    def __init__(self, *args, **kwargs):
        self.priority = int(kwargs.pop("priority", self.default_priority))
        self.config_type = kwargs.pop("config_type", None)
        if self.config_type is None or not isinstance(self.config_type, str):
            raise ValueError("config_type must specified, and be a string")

        if kwargs.pop("get_default", False):
            kwargs["default"] = arghparse.DelayedValue(
                partial(self.store_default, self.config_type,
                        option_string=kwargs.get('option_strings', [None])[0]),
                self.priority)

        self.store_name = kwargs.pop("store_name", False)
        self.writable = kwargs.pop("writable", None)
        self.target = argparse._StoreAction(*args, **kwargs)

        super(StoreConfigObject, self).__init__(*args, **kwargs)

    @staticmethod
    def _choices(sections):
        """Yield available values for a given option."""
        for k, v in sections.iteritems():
            yield k

    def _load_obj(self, sections, name):
        obj_type = self.metavar if self.metavar is not None else self.config_type
        obj_type = obj_type.lower() + ' ' if obj_type is not None else ''

        try:
            val = sections[name]
        except KeyError:
            choices = ', '.join(self._choices(sections))
            if choices:
                choices = ' (available: %s)' % choices

            raise argparse.ArgumentError(
                self, "couldn't find %s%r%s" %
                (obj_type, name, choices))

        if self.writable and getattr(val, 'frozen', False):
            raise argparse.ArgumentError(
                self, "%s%r is readonly" % (obj_type, name))

        if self.store_name:
            return name, val
        return val

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, arghparse.DelayedParse(
            partial(self._real_call, parser, namespace, values, option_string),
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
            raise argparse.ArgumentError(None, "no config found.  Internal bug, or broken on disk configuration.")
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
            raise NoDefaultConfigError(None, msg)
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
        return arghparse.DelayedValue(
            partial(cls._lazy_load_object, config_type, key),
            priority)

    @staticmethod
    def _lazy_load_object(config_type, key, namespace, attr):
        try:
            obj = getattr(namespace.config, config_type)[key]
        except KeyError:
            raise argparse.ArgumentError(
                None, "couldn't find %s %r" % (config_type, attr))
        setattr(namespace, attr, obj)


class StoreRepoObject(StoreConfigObject):

    def __init__(self, *args, **kwargs):
        if 'config_type' in kwargs:
            raise ValueError(
                "StoreRepoObject: config_type keyword is redundant: got %s"
                % (kwargs['config_type'],))
        self.raw = kwargs.pop("raw", False)
        self.domain_forced = 'domain' in kwargs
        self.domain = kwargs.pop('domain', 'domain')
        if self.raw:
            kwargs['config_type'] = 'repo_config'
        else:
            kwargs['config_type'] = 'repo'
        self.allow_name_lookup = kwargs.pop("allow_name_lookup", True)
        StoreConfigObject.__init__(self, *args, **kwargs)

    def _get_sections(self, config, namespace):
        domain = None
        if self.domain:
            domain = getattr(namespace, self.domain, None)
            if domain is None and self.domain_forced:
                raise argparse.ArgumentError(
                    self,
                    "No domain found, but one was forced for %s; "
                    "internal bug.  NS=%s" % (self, namespace))
        if domain is None:
            return StoreConfigObject._get_sections(self, config, namespace)
        return domain.repos_raw if self.raw else domain.repos_configured_filtered

    @staticmethod
    def _choices(sections):
        """Return an iterable of name: location mappings for available repos.

        If a repo doesn't have a proper location just the name is returned.
        """
        for repo_name, repo in sorted(unstable_unique(sections.iteritems())):
            repo_name = getattr(repo, 'repo_id', repo_name)
            if hasattr(repo, 'location'):
                yield '%s:%s' % (repo_name, repo.location)
            else:
                yield repo_name

    def _load_obj(self, sections, name):
        if not self.allow_name_lookup or name in sections:
            return StoreConfigObject._load_obj(self, sections, name)

        # name wasn't found; search for it.
        for repo_name, repo in sections.iteritems():
            if name in repo.aliases:
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
            raise ValueError(
                "multiple domains claim root %r: domains %s" %
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


class BooleanQuery(arghparse.DelayedValue):

    def __init__(self, attrs, klass_type=None, priority=100, converter=None):
        if klass_type == 'and':
            self.klass = packages.AndRestriction
        elif klass_type == 'or':
            self.klass = packages.OrRestriction
        elif callable(klass_type):
            self.klass = klass
        else:
            raise ValueError(
                "klass_type either needs to be 'or', 'and', "
                "or a callable.  Got %r" % (klass_type,))

        if converter is not None and not callable(converter):
            raise ValueError(
                "converter either needs to be None, or a callable;"
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
            if isinstance(val, bool):
                # Skip converter call for disabled boolean actions
                if not val:
                    self.converter = False
            elif isinstance(val, restriction.base):
                l.append(val)
            else:
                l.extend(val)

        if self.converter:
            l = self.converter(l, namespace)

        l = list(iflatten_instance(l, (restriction.base,)))

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
        def query(value):
            return parserestrict.parse_match(value)
        kwargs.setdefault("type", query)
    if kwargs.get('metavar', False) is None:
        del kwargs['metavar']
    else:
        kwargs.setdefault("metavar", dest)
    final_priority = kwargs.pop("final_priority", None)
    final_converter = kwargs.pop("final_converter", None)
    parser.add_argument(*args, **kwargs)
    bool_kwargs = {'converter': final_converter}
    if final_priority is not None:
        bool_kwargs['priority'] = final_priority
    obj = BooleanQuery(list(attrs) + [subattr], klass_type=klass_type, **bool_kwargs)
    # note that dict expansion has to be used here; dest=obj would just set a
    # default named 'dest'
    parser.set_defaults(**{dest: obj})


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
            return import_module(value)
        elif attribute:
            return modules.load_attribute(value)
        return modules.load_any(value)
    except (ImportError, modules.FailedImport) as err:
        compatibility.raise_from(argparse.ArgumentTypeError(str(err)))


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


def store_config(namespace, attr, global_config=()):
    configs = map(
        _convert_config_mods, [namespace.pop('new_config'), namespace.pop('add_config')])
    # add necessary inherits for add_config
    for key, vals in configs[1].iteritems():
        vals.setdefault('inherit', key)

    configs = [{section: basics.ConfigSectionFromStringDict(vals)
                for section, vals in d.iteritems()}
               for d in configs if d]

    config = load_config(
        skip_config_files=namespace.pop('empty_config'),
        prepend_sources=tuple(global_config),
        append_sources=tuple(configs),
        location=namespace.pop('override_config'),
        **vars(namespace))
    setattr(namespace, attr, config)


def _mk_domain(parser):
    parser.add_argument(
        '--domain', get_default=True, config_type='domain',
        action=StoreConfigObject,
        help="domain to use for this operation")


class ArgumentParser(arghparse.ArgumentParser):

    def __init__(self, suppress=False, config=True, domain=True, script=None, **kwds):
        super(ArgumentParser, self).__init__(suppress=suppress, script=script, **kwds)

        if not suppress:
            if config:
                self.add_argument(
                    '--add-config', nargs=3, action='append',
                    metavar=('SECTION', 'KEY', 'VALUE'),
                    help='modify an existing configuration section')
                self.add_argument(
                    '--new-config', nargs=3, action='append',
                    metavar=('SECTION', 'KEY', 'VALUE'),
                    help='add a new configuration section')
                self.add_argument(
                    '--empty-config', action='store_true',
                    help='do not load user/system configuration')
                self.add_argument(
                    '--config', metavar='PATH', dest='override_config',
                    type=arghparse.existent_path,
                    help='override location of config files')

                if script is not None:
                    try:
                        _, script_module = script
                    except TypeError:
                        raise ValueError(
                            "invalid script parameter, should be (__file__, __name__)")
                    project = script_module.split('.')[0]
                else:
                    project = __name__.split('.')[0]

                # TODO: Figure out a better method for plugin registry/loading.
                try:
                    plugins = import_module('.plugins', project)
                    global_config = get_plugins('global_config', plugins)
                    self.set_defaults(config=arghparse.DelayedValue(
                        partial(store_config, global_config=global_config), 0))
                except ImportError:
                    pass

            if domain:
                _mk_domain(self)


def convert_to_restrict(sequence, default=packages.AlwaysTrue):
    """Convert an iterable to a list of atoms, or return the default"""
    l = []
    try:
        for x in sequence:
            l.append(parserestrict.parse_match(x))
    except parserestrict.ParseError as e:
        compatibility.raise_from(
            argparse.ArgumentError(
                "arg %r isn't a valid atom: %s" % (x, e)))
    return l or [default]


class Tool(BaseTool):
    """Pkgcore-specific commandline utility functionality."""

    def parse_args(self, *args, **kwargs):
        """Pass down pkgcore-specific settings to the bash side."""
        options = super(Tool, self).parse_args(*args, **kwargs)

        if self.parser.debug:
            # verbosity level affects debug output
            verbose = getattr(options, 'verbose', None)
            debug_verbosity = verbose if verbose is not None else 1
            # pass down debug setting
            os.environ['PKGCORE_DEBUG'] = str(debug_verbosity)

        if not getattr(options, 'color', True):
            # pass down color setting
            if 'PKGCORE_NOCOLOR' not in os.environ:
                os.environ['PKGCORE_NOCOLOR'] = '1'

        return options

    def handle_exec_exception(self, e):
        """Handle pkgcore-specific runtime exceptions."""
        if isinstance(e, errors.ParsingError):
            if self.parser.debug:
                tb = sys.exc_info()[-1]
                dump_error(e, 'Error while parsing arguments', tb=tb)
            else:
                self.parser.error("config error: %s" % (e,))
        elif isinstance(e, errors.ConfigurationError):
            if self.parser.debug:
                tb = sys.exc_info()[-1]
                dump_error(e, "Error in configuration", handle=self._errfile, tb=tb)
            else:
                excs = list(walk_exception_chain(e))
                # skip the original exception if it was re-raised
                exc = excs[-2] if len(excs) > 1 else excs[-1]
                self.parser.error("config error: %s" % (exc,))
        elif isinstance(e, operations.OperationError):
            tb = sys.exc_info()[-1]
            if not self.parser.debug:
                tb = None
            dump_error(e, "Error running an operation", handle=self._errfile, tb=tb)
        else:
            # exception is unhandled here, fallback to generic handling
            super(Tool, self).handle_exec_exception(e)


# TODO: deprecated wrapper, remove in 0.10.0
def main(parser, args=None, outfile=None, errfile=None):
    """Function to use in an "if __name__ == '__main__'" block in a script.

    Takes an argparser instance and runs it against available args, them,
    taking care of exception handling and some other things.

    Any ConfigurationErrors raised from your function (by the config
    manager) are handled. Other exceptions are not (trigger a traceback).

    :type parser: ArgumentParser instance
    :param parser: Argument parser for external commands or scripts.
    :type args: sequence of strings
    :param args: arguments to parse, defaulting to C{sys.argv[1:]}.
    :type outfile: file-like object
    :param outfile: File to use for stdout, defaults to C{sys.stdout}.
    :type errfile: file-like object
    :param errfile: File to use for stderr, defaults to C{sys.stderr}.
    """
    t = Tool(parser=parser, outfile=outfile, errfile=errfile)
    ret = t(args=args)
    raise SystemExit(ret)
