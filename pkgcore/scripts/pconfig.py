# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Configuration querying utility."""


import traceback

from pkgcore.config import errors, basics
from pkgcore.util import commandline, modules, currying
from pkgcore.plugin import get_plugins


class DescribeClassParser(commandline.OptionParser):

    """Our option parser."""

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if len(args) != 1:
            self.error('need exactly one argument: class to describe.')
        try:
            values.describe_class = modules.load_attribute(args[0])
        except modules.FailedImport, e:
            self.error(str(e))
        return values, ()


def dump_section(config, out, sections):
    out.first_prefix.append('    ')
    out.write('# typename of this section: %s' % (config.type.name,))
    out.write('class %s.%s;' % (config.type.callable.__module__,
                                config.type.callable.__name__))
    if config.default:
        out.write('default true;')
    for key, val in sorted(config.config.iteritems()):
        typename = config.type.types.get(key)
        if typename is None:
            if config.type.allow_unknowns:
                typename = 'str'
            else:
                out.write('# huh, no type set for %s (%r)' % (key, val))
                continue
        out.write('# type: %s' % (typename,))
        if typename.startswith('lazy_refs'):
            typename = 'section_refs'
            val = list(ref.collapse() for ref in val)
        elif typename.startswith('lazy_ref'):
            typename = 'section_ref'
            val = val.collapse()
        if typename == 'str':
            out.write('%s %r;' % (key, val))
        elif typename == 'bool':
            out.write('%s %s;' % (key, bool(val)))
        elif typename == 'list':
            out.write('%s %s;' % (
                    key, ' '.join(repr(string) for string in val)))
        elif typename == 'callable':
            out.write('%s %s.%s' % (key, val.__module__, val.__name__))
        elif typename == 'section_ref' or typename.startswith('ref:'):
            name = sections.get(val)
            if name is None:
                out.write('%s {' % (key,))
                dump_section(val, out, sections)
                out.write('};')
            else:
                out.write('%s %r;' % (key, name))
        elif typename == 'section_refs' or typename.startswith('refs:'):
            out.autoline = False
            out.write('%s' % (key,))
            for i, subconf in enumerate(val):
                name = sections.get(subconf)
                if name is None:
                    out.autoline = True
                    out.write(' {')
                    dump_section(subconf, out, sections)
                    out.autoline = False
                    out.write('}')
                else:
                    out.write(' %r' % (name,))
            out.autoline = True
            out.write(';')
        else:
            out.write('# %s = %r of unknown type %s' % (key, val, typename))
    out.first_prefix.pop()


def classes_main(options, out, err):
    """List all classes referenced by the config."""
    # Not particularly efficient (doesn't memoize already visited configs)
    configmanager = options.config
    classes = set()
    for name in configmanager.sections():
        try:
            config = configmanager.collapse_named_section(name)
        except errors.ConfigurationError:
            if options.debug:
                traceback.print_exc()
            # Otherwise ignore this.
            continue
        classes.add('%s.%s' % (config.type.callable.__module__,
                               config.type.callable.__name__))
        for key, val in config.config.iteritems():
            typename = config.type.types.get(key)
            if typename is None:
                continue
            if typename == 'section_ref' or typename.startswith('ref:'):
                classes.update(get_classes((val,)))
            elif typename == 'section_refs' or typename.startswith('refs:'):
                classes.update(get_classes(val))
            elif typename.startswith('lazy_refs'):
                classes.update(get_classes(c.collapse() for c in val))
            elif typename.startswith('lazy_ref'):
                classes.update(get_classes((val.collapse(),)))
    for classname in sorted(classes):
        out.write(classname)


def write_type(out, type_obj):
    out.write('typename is %s' % (type_obj.name,))
    if type_obj.doc:
        for line in type_obj.doc.split('\n'):
            out.write(line.strip(), wrap=True)
    if type_obj.allow_unknowns:
        out.write('values not listed are handled as strings')
    out.write()
    for name, typename in sorted(type_obj.types.iteritems()):
        out.write('%s: %s' % (name, typename), autoline=False)
        if name in type_obj.required:
            out.write(' (required)', autoline=False)
        if name in type_obj.incrementals:
            out.write(' (incremental)', autoline=False)
        out.write()


def describe_class_main(options, out, err):
    """Describe the arguments a class needs."""
    try:
        type_obj = basics.ConfigType(options.describe_class)
    except errors.TypeDefinitionError:
        out.write('Not a valid type!')
        return 1
    write_type(out, type_obj)


def uncollapsable_main(options, out, err):
    """Show things that could not be collapsed."""
    config = options.config
    for name in config.sections():
        try:
            config.collapse_named_section(name)
        except errors.ConfigurationError, e:
            if options.debug:
                traceback.print_exc()
            else:
                out.write(str(e))
            out.write()


class _TypeNameParser(commandline.OptionParser):

    """Base for subcommands that take an optional type name."""

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(self, values,
                                                             args)
        if len(args) > 1:
            self.error('pass at most one typename')
        if args:
            values.typename = args[0]
        else:
            values.typename = None
        return values, ()


class DumpParser(_TypeNameParser):

    def __init__(self, **kwargs):
        # Make sure we do not pass two description kwargs if kwargs has one.
        kwargs['description'] = (
            'Dump the entire configuration. '
            'The format used is similar to the ini-like default '
            'format, but do not rely on this to always write a '
            'loadable config. There may be quoting issues. '
            'With a typename argument only that type is dumped.')
        kwargs['usage'] = '%prog [options] [typename]'
        _TypeNameParser.__init__(self, **kwargs)


def dump_main(options, out, err):
    """Dump the entire configuration."""
    sections = []
    config = options.config
    if options.typename is None:
        names = config.sections()
    else:
        names = getattr(config, options.typename).iterkeys()
    for name in names:
        try:
            sections.append((name, config.collapse_named_section(name)))
        except errors.ConfigurationError:
            if options.debug:
                traceback.print_exc()
            # Otherwise ignore this.
    sections.sort()
    revmap = dict((config, name) for name, config in sections)
    for name, section in sections:
        out.write('%r {' % (name,))
        dump_section(section, out, revmap)
        out.write('}')
        out.write()


class ConfigurablesParser(_TypeNameParser):

    def __init__(self, **kwargs):
        # Make sure we do not pass two description kwargs if kwargs has one.
        kwargs['description'] = (
            'List registered configurables (may not be complete). '
            'With a typename argument only configurables of that type are '
            'listed.')
        kwargs['usage'] = '%prog [options] [typename]'
        _TypeNameParser.__init__(self, **kwargs)


def configurables_main(options, out, err):
    """List registered configurables."""
    for configurable in get_plugins('configurable'):
        type_obj = basics.ConfigType(configurable)
        if options.typename is not None and type_obj.name != options.typename:
            continue
        out.write(out.bold, '%s.%s' % (
                configurable.__module__, configurable.__name__))
        write_type(out, type_obj)
        out.write()
        out.write()


commandline_commands = {
    'dump': (DumpParser, dump_main),
    'classes': (commandline.OptionParser, classes_main),
    'uncollapsable': (commandline.OptionParser, uncollapsable_main),
    'describe_class': (DescribeClassParser, describe_class_main),
    'configurables': (ConfigurablesParser, configurables_main),
    }
