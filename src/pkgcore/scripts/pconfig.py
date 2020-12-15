"""configuration querying utility"""

__all__ = (
    "get_classes", "dump", "dump_main", "classes", "classes_main",
    "uncollapsable", "uncollapsable_main",
    "describe_class", "describe_class_main",
    "configurables", "configurables_main",
    "dump_uncollapsed", "dump_uncollapsed_main"
)

import textwrap
import traceback
from functools import partial

from snakeoil.errors import dump_error

from ..config import basics, errors
from ..ebuild import atom
from ..plugin import get_plugins
from ..util import commandline


def dump_section(config, out):
    out.first_prefix.append('    ')
    out.write(f'# typename of this section: {config.type.name}')
    out.write(f'class {config.type.callable.__module__}.{config.type.callable.__name__};')
    if config.default:
        out.write('default true;')
    for key, val in sorted(config.config.items()):
        typename = config.type.types.get(key)
        if typename is None:
            if config.type.allow_unknowns:
                typename = 'str'
            else:
                raise ValueError(f'no type set for {key} ({val!r})')
        out.write(f'# type: {typename}')
        if typename.startswith('lazy_refs'):
            typename = typename[5:]
            val = list(ref.collapse() for ref in val)
        elif typename.startswith('lazy_ref'):
            typename = typename[5:]
            val = val.collapse()
        if typename == 'str':
            out.write(f'{key} {val!r};')
        elif typename == 'bool':
            out.write(f'{key} {bool(val)};')
        elif typename == 'list':
            out.write(f"{key} {' '.join(map(repr, val))};")
        elif typename == 'callable':
            out.write(f'{key} {val.__module__}.{val.__name__};')
        elif typename.startswith('ref:'):
            if val.name is None:
                out.write(f'{key} {{')
                dump_section(val, out)
                out.write('};')
            else:
                out.write(f'{key} {val.name!r};')
        elif typename.startswith('refs:'):
            out.autoline = False
            out.write(f'{key}')
            for i, subconf in enumerate(val):
                if subconf.name is None:
                    out.autoline = True
                    out.write(' {')
                    dump_section(subconf, out)
                    out.autoline = False
                    out.write('}')
                else:
                    out.write(f' {subconf.name!r}')
            out.autoline = True
            out.write(';')
        else:
            out.write(f'# {key} = {val!r} of unknown type {typename}')
    out.first_prefix.pop()


def get_classes(configs):
    # Not particularly efficient (doesn't memoize already visited configs)
    classes = set()
    for config in configs:
        classes.add(f'{config.type.callable.__module__}.{config.type.callable.__name__}')
        for key, val in config.config.items():
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


shared_options = (commandline.ArgumentParser(
    config=False, color=False, debug=False, quiet=False, verbose=False,
    version=False, domain=False, add_help=False),)
shared_options_domain = (commandline.ArgumentParser(
    config=False, color=False, debug=False, quiet=False, verbose=False,
    version=False, domain=True, add_help=False),)

pkgcore_opts = commandline.ArgumentParser(domain=False, script=(__file__, __name__))
argparser = commandline.ArgumentParser(
    suppress=True, description=__doc__, parents=(pkgcore_opts,))
subparsers = argparser.add_subparsers(description="configuration related subcommands")
classes = subparsers.add_parser(
    "classes", parents=shared_options,
    description="list all classes referenced by the config")
@classes.bind_main_func
def classes_main(options, out, err):
    """List all classes referenced by the config."""
    configmanager = options.config
    sections = []
    for name in configmanager.sections():
        try:
            sections.append(configmanager.collapse_named_section(name))
        except errors.CollapseInheritOnly:
            pass
        except errors.ConfigurationError:
            pass
    for classname in sorted(get_classes(sections)):
        out.write(classname)


describe_class = subparsers.add_parser(
    "describe_class", parents=shared_options,
    description="describe the arguments a class needs, how to use it in a config")
describe_class.add_argument(
    "target_class", action='store',
    type=partial(commandline.python_namespace_type, attribute=True),
    help="The class to inspect and output details about")
@describe_class.bind_main_func
def describe_class_main(options, out, err):
    """Describe the arguments a class needs."""
    try:
        type_obj = basics.ConfigType(options.target_class)
    except errors.TypeDefinitionError:
        err.write('Not a valid type!')
        return 1
    write_type(out, type_obj)

def write_type(out, type_obj):
    out.write(f'typename is {type_obj.name}')
    if type_obj.doc:
        for line in type_obj.doc.split('\n'):
            out.write(line.strip(), wrap=True)
    if type_obj.allow_unknowns:
        out.write('values not listed are handled as strings')
    out.write()
    for name, typename in sorted(type_obj.types.items()):
        if typename.startswith("lazy_ref:"):
            typename = typename[len("lazy_ref:"):]
        elif typename.startswith("lazy_refs:"):
            typename = typename[len("lazy_refs:"):]
        out.write(f'{name}: {typename}', autoline=False)
        if name in type_obj.required:
            out.write(' (required)', autoline=False)
        out.write()

uncollapsable = subparsers.add_parser(
    "uncollapsable", parents=shared_options,
    description="show configuration objects that could not be collapsed/instantiated")
@uncollapsable.bind_main_func
def uncollapsable_main(options, out, err):
    """Show things that could not be collapsed."""
    config = options.config
    for name in sorted(config.sections()):
        try:
            config.collapse_named_section(name)
        except errors.CollapseInheritOnly:
            pass
        except errors.ConfigurationError as e:
            out.autoline = False
            dump_error(e, f"section {name}", handle=out)
            if options.debug:
                traceback.print_exc()
            out.autoline = True
            out.write()


dump = subparsers.add_parser(
    "dump", parents=shared_options,
    description='dump the entire configuration',
    docs="""
        Dump the entire configuration in a format similar to the ini-like
        default format; however, do not rely on this to always write a loadable
        config. There may be quoting issues. With a typename argument only that
        type is dumped.
    """)
dump.add_argument(
    "typename", nargs="?", action="store", default=None,
    help="if specified, limit output to just config directives of this "
         "type (defaults to showing all types)")
@dump.bind_main_func
def dump_main(options, out, err):
    """Dump the entire configuration."""
    config = options.config
    if options.typename is None:
        names = config.sections()
    else:
        names = iter(getattr(config, options.typename).keys())
    for i, name in enumerate(sorted(names)):
        if i > 0:
            out.write()
        try:
            section = config.collapse_named_section(name)
        except errors.CollapseInheritOnly:
            continue
        except errors.ConfigurationError:
            continue
        out.write(f'{name!r} {{')
        dump_section(section, out)
        out.write('}')


configurables = subparsers.add_parser(
    "configurables", parents=shared_options,
    description='list registered configurables (may not be complete)')
configurables.add_argument(
    "typename", nargs='?', default=None, action='store',
    help="if specified, only output configurables of that type; else output "
         "all configurables")
@configurables.bind_main_func
def configurables_main(options, out, err):
    """List registered configurables."""

    # try and sort this beast.
    def key_func(obj):
        return "%s.%s" % (getattr(obj, '__module__', ''),
                          getattr(obj, '__name__', ''))

    for configurable in sorted(get_plugins('configurable'), key=key_func):
        type_obj = basics.ConfigType(configurable)
        if options.typename is not None and type_obj.name != options.typename:
            continue
        out.write(out.bold, f'{configurable.__module__}.{configurable.__name__}')
        write_type(out, type_obj)
        out.write()
        out.write()


def _dump_uncollapsed_section(config, out, err, section):
    """Write a single section."""
    if isinstance(section, str):
        out.write(f'named section {section!r}')
        return
    for key in sorted(section.keys()):
        kind, value = section.render_value(config, key, 'repr')
        out.write(f'# type: {kind}')
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
                            subname = f'nested section {subnr + 1}'
                            out.write(subname)
                            out.write('=' * len(subname))
                            _dump_uncollapsed_section(config, out, err, subsection)
                            out.write()
                    finally:
                        out.first_prefix.pop()
            continue
        out.write(f'{key!r} = ', autoline=False)
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
            err.error(f'unsupported type {kind!r}')

dump_uncollapsed = subparsers.add_parser(
    "dump-uncollapsed", parents=shared_options,
    description="dump the configuration in a raw, uncollapsed form",
    docs="""
        Dump the configuration in a raw, uncollapsed form not directly usable
        as a configuration file, mainly used for inspection.
    """)
@dump_uncollapsed.bind_main_func
def dump_uncollapsed_main(options, out, err):
    """dump the configuration in a raw, uncollapsed form.
    Not directly usable as a configuration file, mainly used for inspection
    """
    out.write(textwrap.dedent('''\
        # Warning:
        # Do not copy this output to a configuration file directly,
        # because the types you see here are only guesses.
        # A value used as "list" in the collapsed config will often
        # show up as "string" here and may need to be converted
        # (for example from space-separated to comma-separated)
        # to work in a config file with a different format.
        '''))
    for i, source in enumerate(options.config.configs):
        s = f'Source {i + 1}'
        out.write(out.bold, '*' * len(s))
        out.write(out.bold, s)
        out.write(out.bold, '*' * len(s))
        out.write()
        for name, section in sorted(source.items()):
            out.write(f'{name}')
            out.write('=' * len(name))
            _dump_uncollapsed_section(options.config, out, err, section)
            out.write()

package = subparsers.add_parser(
    "package", parents=shared_options_domain,
    description="invoke a packages custom configuration scripts")
commandline.make_query(
    package, nargs='+', dest='query',
    help="restrictions/atoms; matching installed packages will be configured")
@package.bind_main_func
def package_func(options, out, err):
    matched = True
    domain = options.domain
    for pkg in domain.installed_repos.combined.itermatch(options.query):
        matched = True
        ops = domain.pkg_operations(pkg)
        if not ops.supports("configure"):
            out.write(f"package {pkg}: nothing to configure, ignoring")
            continue
        out.write(f"package {pkg}: configuring...")
        ops.configure()
    if not matched:
        out.write("no packages matched")
    return 1


world = subparsers.add_parser(
    "world", parents=shared_options_domain,
    description="inspect and modify the world file")
world_modes = world.add_argument_group(
    "command modes",
    description="""
        These options are directives for what to do with the world file. You
        can do multiple operations in a single invocation.  For example, you
        can have `--add x11-wm/fluxbox --remove gnome-base/gnome -l` to add
        fluxbox, remove gnome, and list the world file contents all in one
        call.
    """)
world_modes.add_argument(
    '-l', '--list', action='store_true',
    help="List the current world file contents for this domain.")
world_modes.add_argument(
    '-r', '--remove', action='append', type=atom.atom,
    help="Remove an entry from the world file.  Can be specified multiple times.")
world_modes.add_argument(
    '-a', '--add', action='append', type=atom.atom,
    help="Add an entry to the world file.  Can be specified multiple times.")

world.set_defaults(
    world=commandline.StoreConfigObject.lazy_load_object('pkgset', 'world', 99))
@world.bind_main_func
def world_func(options, out, err):
    world_file = options.world

    if options.remove:
        for item in options.remove:
            world_file.remove(item)

    if options.add:
        for item in options.add:
            world_file.add(item)

    if options.remove or options.add:
        world_file.flush()

    if options.list:
        out.write("\n".join(map(str, sorted(world_file))))
        return 0
