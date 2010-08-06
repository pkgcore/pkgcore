# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Configuration querying utility."""

__all__ = ("get_classes", "dump_main", "classes_main", "uncollapsable_main",
    "DescribeClassParser", "describe_class_main", "ConfigurablesParser",
    "configurables_main", "dump_uncollapsed_main"
)

import traceback

from pkgcore.config import errors, basics
from pkgcore.plugin import get_plugins
from pkgcore.util import commandline
from snakeoil import modules

class DescribeClassParser(commandline.OptionParser):

    """Our option parser."""

    def _check_values(self, values, args):
        if len(args) != 1:
            self.error('need exactly one argument: class to describe.')
        try:
            values.describe_class = modules.load_attribute(args[0])
        except modules.FailedImport, e:
            self.error(str(e))
        return values, ()


def dump_section(config, out):
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
                raise ValueError('no type set for %s (%r)' % (key, val))
        out.write('# type: %s' % (typename,))
        if typename.startswith('lazy_refs'):
            typename = typename[5:]
            val = list(ref.collapse() for ref in val)
        elif typename.startswith('lazy_ref'):
            typename = typename[5:]
            val = val.collapse()
        if typename == 'str':
            out.write('%s %r;' % (key, val))
        elif typename == 'bool':
            out.write('%s %s;' % (key, bool(val)))
        elif typename == 'list':
            out.write('%s %s;' % (
                    key, ' '.join(repr(string) for string in val)))
        elif typename == 'callable':
            out.write('%s %s.%s;' % (key, val.__module__, val.__name__))
        elif typename.startswith('ref:'):
            if val.name is None:
                out.write('%s {' % (key,))
                dump_section(val, out)
                out.write('};')
            else:
                out.write('%s %r;' % (key, val.name))
        elif typename.startswith('refs:'):
            out.autoline = False
            out.write('%s' % (key,))
            for i, subconf in enumerate(val):
                if subconf.name is None:
                    out.autoline = True
                    out.write(' {')
                    dump_section(subconf, out)
                    out.autoline = False
                    out.write('}')
                else:
                    out.write(' %r' % (subconf.name,))
            out.autoline = True
            out.write(';')
        else:
            out.write('# %s = %r of unknown type %s' % (key, val, typename))
    out.first_prefix.pop()


def get_classes(configs):
    # Not particularly efficient (doesn't memoize already visited configs)
    classes = set()
    for config in configs:
        classes.add('%s.%s' % (config.type.callable.__module__,
                               config.type.callable.__name__))
        for key, val in config.config.iteritems():
            typename = config.type.types.get(key)
            if typename is None:
                continue
            if typename.startswith('ref:'):
                classes.update(get_classes((val,)))
            elif typename.startswith('refs:'):
                classes.update(get_classes(val))
            elif typename.startswith('lazy_refs'):
                classes.update(get_classes(c.collapse() for c in val))
            elif typename.startswith('lazy_ref'):
                classes.update(get_classes((val.collapse(),)))
    return classes

def classes_main(options, out, err):
    """List all classes referenced by the config."""
    configmanager = options.config
    sections = []
    for name in configmanager.sections():
        try:
            sections.append(configmanager.collapse_named_section(name))
        except errors.CollapseInheritOnly:
            pass
    for classname in sorted(get_classes(sections)):
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
        out.write()


def describe_class_main(options, out, err):
    """Describe the arguments a class needs."""
    try:
        type_obj = basics.ConfigType(options.describe_class)
    except errors.TypeDefinitionError:
        err.write('Not a valid type!')
        return 1
    write_type(out, type_obj)


def uncollapsable_main(options, out, err):
    """Show things that could not be collapsed."""
    config = options.config
    for name in config.sections():
        try:
            config.collapse_named_section(name)
        except errors.CollapseInheritOnly:
            pass
        except errors.ConfigurationError, e:
            if options.debug:
                traceback.print_exc()
            else:
                out.write(str(e))
            out.write()


class _TypeNameParser(commandline.OptionParser):

    """Base for subcommands that take an optional type name."""

    def _check_values(self, values, args):
        if len(args) > 1:
            self.error('pass at most one typename')
        if args:
            values.typename = args[0]
        else:
            values.typename = None
        return values, ()


class DumpParser(_TypeNameParser):
    description = ('Dump the entire configuration.  The format used is similar '
        'to the ini-like default format, but do not rely on this to always '
        'write a loadable config. There may be quoting issues.  With a '
        'typename argument only that type is dumped.')
    usage = '%prog [options] [typename]'


def dump_main(options, out, err):
    """Dump the entire configuration."""
    config = options.config
    if options.typename is None:
        names = config.sections()
    else:
        names = getattr(config, options.typename).iterkeys()
    for name in sorted(names):
        try:
            section = config.collapse_named_section(name)
        except errors.CollapseInheritOnly:
            continue
        out.write('%r {' % (name,))
        dump_section(section, out)
        out.write('}')
        out.write()


class ConfigurablesParser(_TypeNameParser):
    description = ('List registered configurables (may not be complete).  '
        'With a typename argument only configurables of that type are listed.')


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


def _dump_uncollapsed_section(config, out, err, section):
    """Write a single section."""
    if isinstance(section, basestring):
        out.write('named section %r' % (section,))
        return
    for key in sorted(section.keys()):
        kind, value = section.get_value(config, key, 'repr')
        out.write('# type: %s' % (kind,))
        if kind == 'list':
            for name, val in zip((
                    key + '.prepend', key, key + '.append'), value):
                if val:
                    out.write(
                        repr(name), ' = ', ' '.join(repr(v) for v in val))
            continue
        if kind in ('refs', 'str'):
            for name, val in zip((
                    key + '.prepend', key, key + '.append'), value):
                if not val:
                    continue
                out.write(repr(name), ' = ', autoline=False)
                if kind == 'str':
                    out.write(repr(val))
                else:
                    out.write()
                    out.first_prefix.append('    ')
                    try:
                        for subnr, subsection in enumerate(val):
                            subname = 'nested section %s' % (subnr + 1,)
                            out.write(subname)
                            out.write('=' * len(subname))
                            _dump_uncollapsed_section(config, out, err, subsection)
                            out.write()
                    finally:
                        out.first_prefix.pop()
            continue
        out.write('%r = ' % (key,), autoline=False)
        if kind == 'callable':
            out.write(value.__module__, value.__name__)
        elif kind == 'bool':
            out.write(str(value))
        elif kind == 'ref':
            out.first_prefix.append('    ')
            try:
                out.write()
                _dump_uncollapsed_section(config, out, err, value)
            finally:
                out.first_prefix.pop()
        else:
            err.error('unsupported type %r' % (kind,))


def dump_uncollapsed_main(options, out, err):
    """dump the configuration in a raw, uncollapsed form.
    Not directly usable as a configuration file, mainly used for inspection
    """
    out.write('''# Warning:
# Do not copy this output to a configuration file directly,
# because the types you see here are only guesses.
# A value used as "list" in the collapsed config will often
# show up as "string" here and may need to be converted
# (for example from space-separated to comma-separated)
# to work in a config file with a different format.
''')
    for i, source in enumerate(options.config.configs):
        s = 'Source %s' % (i + 1,)
        out.write(out.bold, '*' * len(s))
        out.write(out.bold, s)
        out.write(out.bold, '*' * len(s))
        out.write()
        for name, section in sorted(source.iteritems()):
            out.write('%s' % (name,))
            out.write('=' * len(name))
            _dump_uncollapsed_section(options.config, out, err, section)
            out.write()


commandline_commands = {
    'dump': (DumpParser, dump_main),
    'classes': (commandline.OptionParser, classes_main),
    'uncollapsable': (commandline.OptionParser, uncollapsable_main),
    'describe_class': (DescribeClassParser, describe_class_main),
    'configurables': (ConfigurablesParser, configurables_main),
    'dump-uncollapsed': (commandline.OptionParser, dump_uncollapsed_main),
    }
