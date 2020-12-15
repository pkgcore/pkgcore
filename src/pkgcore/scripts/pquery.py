"""package querying interface

pquery is used to extract various kinds of information about either installed
or uninstalled packages. From an overall usage standpoint it is similar to
equery, but it can do things equery cannot do and is a bit more flexible.

What pquery does is select packages from one or more repos that match
a boolean combination of restrictions, then print selected information about
those packages. It is important to understand that the information printing and
repo selection options are almost completely separate from the
restriction options. The only exception to that is that restrictions on
contents automatically select the vdb (installed packages) repo, since
running them on source repos makes no sense.
"""

import errno
import os
from functools import partial

from snakeoil.cli import arghparse
from snakeoil.formatters import decorate_forced_wrapping
from snakeoil.osutils import pjoin, sizeof_fmt
from snakeoil.sequences import iter_stable_unique

from .. import const
from ..ebuild import atom, conditionals
from ..fs import fs as fs_module
from ..repository import multiplex
from ..repository.util import get_raw_repos, get_virtual_repos
from ..restrictions import boolean, packages, values
from ..util import commandline
from ..util import packages as pkgutils
from ..util import parserestrict


class DataSourceRestriction(values.base):
    """Turn a data_source into a line iterator and apply a restriction."""

    def __init__(self, childrestriction, **kwargs):
        super().__init__(**kwargs)
        self.restriction = childrestriction

    def __str__(self):
        return f'DataSourceRestriction: {self.restriction} negate={self.negate}'

    def __repr__(self):
        if self.negate:
            string = '<%s restriction=%r negate @%#8x>'
        else:
            string = '<%s restriction=%r @%#8x>'
        return string % (self.__class__.__name__, self.restriction, id(self))

    def match(self, value):
        return self.restriction.match(iter(value.text_fileobj())) ^ self.negate

    __hash__ = object.__hash__


dep_attrs = ['bdepend', 'depend', 'rdepend', 'pdepend']
metadata_attrs = dep_attrs
dep_attrs += list(f'raw_{x}' for x in dep_attrs)
dep_formatted_attrs = dep_attrs + ['restrict']
dep_formatted_attrs = frozenset(dep_attrs + ['restrict'])
dep_attrs = tuple(sorted(dep_attrs))

metadata_attrs += [
    'defined_phases',
    'description',
    'eapi',
    'fetchables',
    'distfiles',
    'homepage',
    'inherited',
    'iuse',
    'keywords',
    'license',
    'properties',
    'required_use',
    'restrict',
    'slot',
    'subslot',
    'use',
]
metadata_attrs = tuple(sorted(metadata_attrs))

printable_attrs = tuple(dep_formatted_attrs) + metadata_attrs
printable_attrs += (
    'all',
    'alldepends',
    'allmetadata',
    'category',
    'cbuild',
    'chost',
    'ctarget',
    'environment',
    'files',
    'fullver',
    'longdescription',
    'maintainers',
    'package',
    'path',
    'raw_alldepends',
    'repo',
    'revision',
    'source_repository',
    'uris',
    'version',
)
printable_attrs = tuple(sorted(set(printable_attrs)))


def stringify_attr(config, pkg, attr):
    """Grab a package attr and convert it to a string."""
    # config is currently unused but may affect display in the future.
    if attr in ('files', 'uris'):
        data = get_pkg_attr(pkg, 'fetchables')
        if data is None:
            return 'MISSING'
        if attr == 'files':
            def _format(node):
                return node.filename
        else:
            def _format(node):
                return ' '.join(node.uri)
        return conditionals.stringify_boolean(data, _format)

    if attr == 'use':
        # Combine a list of all enabled (including irrelevant) and all
        # available flags into a "enabled -disabled" style string.
        use = set(get_pkg_attr(pkg, 'use', ()))
        iuse = get_pkg_attr(pkg, 'iuse_stripped', ())
        result = sorted(iuse & use) + sorted('-' + val for val in (iuse - use))
        return ' '.join(result)

    value = get_pkg_attr(pkg, attr)
    if value is None:
        return 'MISSING'

    if attr in ('iuse', 'properties', 'defined_phases', 'inherited'):
        return ' '.join(sorted(str(v) for v in value))
    if attr in ('maintainers', 'homepage'):
        return ' '.join(str(v) for v in value)
    if attr == 'longdescription':
        return str(value)
    if attr == 'keywords':
        return ' '.join(sorted(value, key=lambda x: x.lstrip("~")))
    if attr == 'distfiles':
        # collapse depsets for raw repo pkgs -- no USE flags are enabled
        if isinstance(value, conditionals.DepSet):
            value = value.evaluate_depset([])
        return ' '.join(value)
    if attr == 'environment':
        return value.text_fileobj().read()
    if attr == 'repo':
        return str(get_pkg_attr(value, 'repo_id', 'no repo id'))
    # hackish.
    return str(value)


def _default_formatter(out, node):
    out.write(node, autoline=False)
    return False


@decorate_forced_wrapping(False)
def format_depends(out, node, func=_default_formatter):
    """Pretty-print a depset to a formatter.

    :param out: formatter.
    :param node: a :obj:`conditionals.DepSet`.
    :param func: callable taking a formatter and a depset payload.
        If it can format its value in a single line it should do that
        without writing a newline and return C{False}.
        If it needs multiple lines it should first write a newline, not write
        a terminating newline, and return C{True}.
    :return: The same kind of boolean func should return.
    """
    # Do this first since if it is a DepSet it is also an
    # AndRestriction (DepSet subclasses that).
    if isinstance(node, conditionals.DepSet):
        if not node.restrictions:
            return False
        if len(node.restrictions) == 1:
            # Force a newline first.
            out.write()
            return _internal_format_depends(out, node.restrictions[0], func)
        out.write()
        for child in node.restrictions[:-1]:
            _internal_format_depends(out, child, func)
            out.write()
        _internal_format_depends(out, node.restrictions[-1], func)
        return True
    # weird..
    return _internal_format_depends(out, node, func)


def _internal_format_depends(out, node, func):
    prefix = None
    if isinstance(node, boolean.OrRestriction):
        prefix = '|| ('
        children = node.restrictions
    elif (isinstance(node, boolean.AndRestriction) and not
          isinstance(node, atom.atom)):
        prefix = '('
        children = node.restrictions
    elif isinstance(node, packages.Conditional):
        assert len(node.restriction.vals) == 1
        prefix = '%s%s? (' % (node.restriction.negate and '!' or '',
                              list(node.restriction.vals)[0])
        children = node.payload
    if prefix:
        children = list(children)
        if len(children) == 1:
            out.write(prefix, ' ', autoline=False)
            out.first_prefix.append('    ')
            newline = _internal_format_depends(out, children[0], func)
            out.first_prefix.pop()
            if newline:
                out.write()
                out.write(')', autoline=False)
                return True
            else:
                out.write(' )', autoline=False)
                return False
        else:
            out.write(prefix)
            out.first_prefix.append('    ')
            for child in children:
                _internal_format_depends(out, child, func)
                out.write()
            out.first_prefix.pop()
            out.write(')', autoline=False)
            return True
    else:
        return func(out, node)


def format_attr(config, out, pkg, attr):
    """Grab a package attr and print it through a formatter."""
    # config is currently unused but may affect display in the future.
    if attr in dep_formatted_attrs:
        data = get_pkg_attr(pkg, attr)
        if data is None:
            out.write('MISSING')
        else:
            out.first_prefix.append('        ')
            if config.highlight_dep:
                def _format(out, node):
                    for highlight in config.highlight_dep:
                        if highlight.intersects(node):
                            out.write(out.bold, out.fg('cyan'), node,
                                      autoline=False)
                            return
                    out.write(node, autoline=False)
                format_depends(out, data, _format)
            else:
                format_depends(out, data)
            out.first_prefix.pop()
            out.write()
    elif attr in ('files', 'uris'):
        data = get_pkg_attr(pkg, 'fetchables')
        if data is None:
            out.write('MISSING')
            return
        if attr == 'files':
            def _format(out, node):
                out.write(node.filename, autoline=False)
        else:
            def _format(out, node):
                if not node.uri:
                    return False
                if len(node.uri) == 1:
                    out.write(node.uri[0], autoline=False)
                    return False
                out.write('|| (')
                out.first_prefix.append('    ')
                for uri in node.uri:
                    out.write(uri)
                out.first_prefix.pop()
                out.write(')', autoline=False)
                return True
        out.first_prefix.append('        ')
        format_depends(out, data, _format)
        out.first_prefix.pop()
        out.write()
    else:
        out.write(stringify_attr(config, pkg, attr))


def print_package(options, out, err, pkg):
    """Print a package."""
    if options.verbosity > 0:
        green = out.fg('green')
        out.write(out.bold, green, ' * ', out.fg(), pkg.cpvstr)
        out.wrap = True
        out.later_prefix = ['                  ']
        for attr in options.attr:
            out.write(green, f'     {attr}: ', out.fg(), autoline=False)
            format_attr(options, out, pkg, attr)
        for revdep in options.print_revdep:
            for name in dep_attrs:
                depset = get_pkg_attr(pkg, name)
                find_cond = getattr(depset, 'find_cond_nodes', None)
                if find_cond is None:
                    out.write(
                        green, '     revdep: ', out.fg(), name, ' on ',
                        str(revdep))
                    continue
                for key, restricts in depset.find_cond_nodes(depset.restrictions, True):
                    if not restricts and key.intersects(revdep):
                        out.write(
                            green, '     revdep: ', out.fg(), name, ' on ',
                            autoline=False)
                        if key == revdep:
                            # this is never reached...
                            out.write(out.bold, str(revdep))
                        else:
                            out.write(
                                str(revdep), ' through dep ', out.bold,
                                str(key))
                for key, restricts in depset.node_conds.items():
                    if key.intersects(revdep):
                        out.write(
                            green, '     revdep: ', out.fg(), name, ' on ',
                            autoline=False)
                        if key == revdep:
                            out.write(
                                out.bold, str(revdep), out.reset,
                                autoline=False)
                        else:
                            out.write(
                                str(revdep), ' through dep ', out.bold,
                                str(key), out.reset, autoline=False)
                        out.write(' if USE matches one of:')
                        for r in restricts:
                            out.write('                  ', str(r))
        out.write()
        out.later_prefix = []
        out.wrap = False
    elif options.one_attr:
        if options.atom:
            out.write('=', autoline=False)
        if options.atom or options.cpv:
            out.write(pkg.cpvstr, autoline=False)
            if options.display_slot:
                out.write(':', pkg.slot, autoline=False)
            if options.display_repo:
                out.write('::', pkg.repo.repo_id, autoline=False)
            out.write('|', autoline=False)
        out.write(stringify_attr(options, pkg, options.one_attr))
    else:
        printed_something = False
        out.autoline = False
        if (not options.contents) or options.cpv:
            printed_something = True
            if options.atom:
                out.write('=')
            out.write(pkg.cpvstr)
            if options.display_slot:
                out.write(':', pkg.slot)
            if options.display_repo:
                out.write('::', pkg.repo.repo_id)
        for attr in options.attr:
            if printed_something:
                out.write(' ')
            printed_something = True
            attr_str = stringify_attr(options, pkg, attr)
            out.write(f'{attr}="{attr_str}"')
        for revdep in options.print_revdep:
            for name in dep_attrs:
                depset = get_pkg_attr(pkg, name)
                if getattr(depset, 'find_cond_nodes', None) is None:
                    # TODO maybe be smarter here? (this code is
                    # triggered by virtuals currently).
                    out.write(f' {name} on {revdep}')
                    continue
                for key, restricts in depset.find_cond_nodes(depset.restrictions, True):
                    if not restricts and key.intersects(revdep):
                        out.write(f' {name} on {revdep} through {key}')
                for key, restricts in depset.node_conds.items():
                    if key.intersects(revdep):
                        restricts = ' or '.join(map(str, restricts))
                        out.write(f' {name} on {revdep} through {key} if USE {restricts},')
        # If we printed anything at all print the newline now
        out.autoline = True
        if printed_something:
            out.write()

    if options.contents:
        color = {
            fs_module.fsDir: [out.bold, out.fg('blue')],
            fs_module.fsLink: [out.bold, out.fg('cyan')],
        }
        for obj in sorted(obj for obj in get_pkg_attr(pkg, 'contents', ())):
            if options.color:
                out.write(*(color.get(obj.__class__, []) + [obj] + [out.reset]))
            else:
                out.write(f'{obj!r}')

    if options.size:
        size = 0
        files = 0
        for location in (obj.location for obj in get_pkg_attr(pkg, 'contents', ())):
            files += 1
            size += os.lstat(location).st_size
        out.write(f'Total files: {files}')
        out.write(f'Total size: {sizeof_fmt(size)}')


def print_packages_noversion(options, out, err, pkgs):
    """Print a summary of all versions for a single package."""
    if options.verbosity > 0:
        green = out.fg('green')
        out.write(out.bold, green, ' * ', out.fg(), pkgs[0].key)
        out.wrap = True
        out.later_prefix = ['                  ']
        versions = ' '.join(pkg.fullver for pkg in sorted(pkgs))
        out.write(green, '     versions: ', out.fg(), versions)
        # If we are already matching on all repos we do not need to duplicate.
        if not options.all_repos:
            versions = sorted(
                pkg.fullver for repo in options.domain.installed_repos
                for pkg in repo.itermatch(pkgs[0].unversioned_atom))
            if versions:
                out.write(green, '     installed: ', out.fg(), ' '.join(versions))
        for attr in options.attr:
            out.write(green, f'     {attr}: ', out.fg(),
                      stringify_attr(options, pkgs[-1], attr))
        out.write()
        out.wrap = False
        out.later_prefix = []
    elif options.one_attr:
        if options.atom:
            out.write('=', autoline=False)
        if options.atom or options.cpv:
            out.write(pkgs[0].key, autoline=False)
            if options.display_slot:
                out.write(':', pkgs[0].slot, autoline=False)
            if options.display_repo:
                out.write('::', pkgs[0].repo.repo_id, autoline=False)
            out.write('|', autoline=False)
        out.write(stringify_attr(options, pkgs[-1], options.one_attr))
    else:
        out.autoline = False
        out.write(pkgs[0].key)
        if options.display_slot:
            out.write(':', pkgs[0].slot, autoline=False)
        if options.display_repo:
            out.write('::', pkgs[0].repo.repo_id, autoline=False)
        for attr in options.attr:
            attr_str = stringify_attr(options, pkgs[-1], attr)
            out.write(f' {attr}="{attr_str}"')
        out.autoline = True
        out.write()


# note the usage of priorities throughout this argparse setup;
# priority 0 (commandline sets this):
#  basically, sort the config first (additions/removals/etc),
# priority 30:
#   sort the repos
# priority 50:
#  sort the query args individually (potentially accessing the config) along
#  or lines for each (thus multiple revdep args are or'd together)
# priority 90:
#  finally generate a final query object, a boolean and of all previous
#  queries.
# priority 100:
#  default priority for DelayedValue; anything else is setup then.

argparser = commandline.ArgumentParser(
    domain=True, description=__doc__, script=(__file__, __name__))

repo_group = argparser.add_argument_group(
    'repository matching options',
    description='options controlling which repos to inspect')
repo_group.add_argument(
    '--raw', action='store_true', default=False,
    help="disable configuration filtering",
    docs="""
        Disable configuration filtering that forces raw dependencies to be
        used, rather than the dependencies rendered via your USE configuration.
        Primarily useful for people who need to look under the hood- ebuild
        devs, PM tool authors, etc. Note this option ignores --domain if is
        specified.
    """)
repo_group.add_argument(
    '--unfiltered', action='store_true', default=False,
    help="disable all license and visibility filtering",
    docs="""
        Disable all package filtering mechanisms such as ACCEPT_KEYWORDS,
        ACCEPT_LICENSE, and package.mask.
    """)
repo_group.add_argument(
    '--virtuals', action='store', choices=('only', 'disable'),
    help='only match virtuals or disable virtuals matching entirely',
    docs="""
        This option requires one of two arguments, either 'only' or 'disable',
        which causes only virtuals to be matched or disables virtuals matching
        entirely, respectively.

        By default, virtuals are included during matching.
    """)


class RawAwareStoreRepoObject(commandline.StoreRepoObject):
    """Custom implementation that is aware of the --raw and --unfiltered options."""

    def _get_sections(self, config, namespace):
        if namespace.raw:
            self.repo_key = 'repos_raw'
        elif namespace.unfiltered:
            self.repo_key = 'unfiltered_repos'
        else:
            self.repo_key = 'repos'
        return super()._get_sections(config, namespace)

repo_mux = repo_group.add_mutually_exclusive_group()
# TODO: update docs when binpkg/vdb repos are configured via repos.conf
repo_mux.add_argument(
    '-r', '--repo', action=RawAwareStoreRepoObject,
    priority=29, allow_external_repos=True,
    help='repo to search (default from domain if omitted)',
    docs="""
        Select the repo to search in for matches. This includes all the
        configured repos in repos.conf as well as the special keywords binpkg,
        provided, and vdb that search the configured binary package repo,
        package.provided, and installed packages, respectively.

        By default, all configured repos except the vdb will be searched when
        this option isn't specified.
    """)
repo_mux.add_argument(
    '-E', '--ebuild-repos', action='store_true',
    help='search all ebuild repos',
    docs="Search within all ebuild repos, all non-ebuild repos are skipped.")
repo_mux.add_argument(
    '-B', '--binary-repos', action='store_true',
    help='search all binary repos',
    docs="Search within all binary repos, all non-binary repos are skipped.")
repo_mux.add_argument(
    '-I', '--installed', action='store_true',
    help='search installed packages',
    docs="Search within installed packages (alias for '--repo vdb').")
repo_mux.add_argument(
    '-A', '--all-repos', action='store_true',
    help='search all repos',
    docs="Search all available repos including the vdb.")


@argparser.bind_delayed_default(30, 'repos')
def setup_repos(namespace, attr):
    # Get repo(s) to operate on.
    if namespace.repo:
        # The store repo machinery handles --raw and --unfiltered for
        # us, thus it being the first check.
        repos = [namespace.repo]
    elif (namespace.contents or namespace.size or namespace._owns or
            namespace._owns_re or namespace.installed):
        repos = namespace.domain.installed_repos
    elif namespace.unfiltered:
        if namespace.all_repos:
            repos = list(namespace.domain.installed_repos)
            repos.extend(namespace.domain.unfiltered_repos)
        elif namespace.ebuild_repos:
            repos = namespace.domain.ebuild_repos_raw
        elif namespace.binary_repos:
            repos = namespace.domain.binary_repos_raw
        else:
            repos = namespace.domain.unfiltered_repos
    elif namespace.all_repos:
        repos = namespace.domain.repos
    elif namespace.ebuild_repos:
        repos = namespace.domain.ebuild_repos
    elif namespace.binary_repos:
        repos = namespace.domain.binary_repos
    else:
        repos = namespace.domain.source_repos

    if namespace.raw or namespace.virtuals:
        repos = get_raw_repos(repos)
    if namespace.virtuals:
        repos = get_virtual_repos(
            repos, namespace.virtuals == 'only')
    setattr(namespace, attr, repos)

query = argparser.add_argument_group(
    'package matching options',
    docs="""
        Each option specifies a restriction packages must match. Specifying
        the same option twice means "or" unless stated otherwise. Specifying
        multiple types of restrictions means "and" unless stated otherwise.
    """)

# for queries, use add_query always; this has the bookkeeping
# necessary to ensure the sub-query gets bound into the
# finalized query
_query_items = []
def add_query(*args, **kwds):
    if 'dest' not in kwds:
        # auto-determine destination name from long option(s)
        dest = [x for x in args if x.startswith(argparser.prefix_chars * 2) and len(x) > 2]
        if not dest:
            raise ValueError(f"no valid options for query dest names: {', '.join(args)}")
        dest = dest[0].lstrip(argparser.prefix_chars)
        kwds['dest'] = dest.replace('-', '_')
    _query_items.append(kwds['dest'])
    kwds.setdefault('final_priority', 50)
    if kwds.get('action', None) == 'append':
        kwds.setdefault('default', [])
    commandline.make_query(query, *args, **kwds)

def bind_add_query(*args, **kwds):
    def f(functor):
        kwds[kwds.pop('bind', 'type')] = functor
        add_query(*args, **kwds)
        return functor
    return f

@bind_add_query(
    nargs='*', dest='matches', metavar='TARGET',
    bind='final_converter', type=None,
    help="extended atom matching of pkgs")
def matches_finalize(targets, namespace):
    repos = multiplex.tree(*namespace.repos)

    # If current working dir is in a repo, build a path restriction; otherwise
    # match everything.
    if not targets:
        cwd = os.getcwd()
        if cwd in repos:
            targets = [cwd]
        else:
            return []

    restrictions = []
    for target in targets:
        try:
            restrictions.append(parserestrict.parse_match(target))
        except parserestrict.ParseError as e:
            if os.path.exists(target):
                try:
                    restrictions.append(repos.path_restrict(target))
                except ValueError as e:
                    argparser.error(e)
            else:
                argparser.error(e)
    if restrictions:
        return packages.OrRestriction(*restrictions)
    return []

add_query(
    '--all', action='append_const',
    const=packages.AlwaysTrue, type=None,
    help='match all packages',
    docs="""
        Match all packages which is equivalent to "pquery *". Note that if no
        query options are specified, this option is enabled.
    """)
add_query(
    '--has-use', action='append',
    type=parserestrict.comma_separated_containment('iuse_stripped'),
    help='exact string match on a USE flag')
add_query(
    '--license', action='append',
    type=parserestrict.comma_separated_containment('license'),
    help='exact match on a license')

query.add_argument(
    '--revdep', nargs=1,
    action=arghparse.Expansion,
    subst=(('--restrict-revdep', '%(0)s'), ('--print-revdep', '%(0)s')),
    help='shorthand for --restrict-revdep atom --print-revdep atom',
    docs="""
        An alias for '--restrict-revdep atom --print-revdep atom', but note
        that --print-revdep is slow so use --restrict-revdep if you just need a
        list.
    """)

query.add_argument(
    '--revdep-pkgs', nargs=1,
    action=arghparse.Expansion,
    subst=(('--restrict-revdep-pkgs', '%(0)s'), ('--print-revdep', '%(0)s')),
    help='shorthand for --restrict-revdep-pkgs atom --print-revdep atom',
    docs="""
        An alias for '--restrict-revdep-pkgs atom --print-revdep atom', but
        note that --print-revdep is slow so use --restrict-revdep if you just
        need a list.
    """)

@bind_add_query(
    '--restrict-revdep', action='append', default=[],
    help='dependency on an atom')
def parse_revdep(value):
    """Value should be an atom, packages with deps intersecting that match."""
    try:
        targetatom = atom.atom(value)
    except atom.MalformedAtom as e:
        raise argparser.error(e)
    val_restrict = values.FlatteningRestriction(
        atom.atom,
        values.AnyMatch(values.FunctionRestriction(targetatom.intersects)))
    return packages.OrRestriction(*list(
        packages.PackageRestriction(dep, val_restrict)
        for dep in ('bdepend', 'depend', 'rdepend', 'pdepend')))

def _revdep_pkgs_match(pkgs, value):
    return any(value.match(pkg) for pkg in pkgs)

@bind_add_query(
    '--restrict-revdep-pkgs', action='append', type=atom.atom,
    default=[], bind='final_converter',
    help='dependency on pkgs that match a specific atom')
def revdep_pkgs_finalize(sequence, namespace):
    if not sequence:
        return []
    l = []
    for atom_inst in sequence:
        for repo in namespace.repos:
            l.extend(repo.itermatch(atom_inst))
    # have our pkgs; now build the restrict.
    any_restrict = values.AnyMatch(
        values.FunctionRestriction(partial(_revdep_pkgs_match, tuple(l))))
    r = values.FlatteningRestriction(atom.atom, any_restrict)
    return list(packages.PackageRestriction(dep, r)
                for dep in ('bdepend', 'depend', 'rdepend', 'pdepend'))

@bind_add_query(
    '-S', '--description', action='append',
    help='regexp search on description and longdescription')
def parse_description(value):
    """Value is used as a regexp matching description or longdescription."""
    matcher = values.StrRegex(value, case_sensitive=False)
    return packages.OrRestriction(*list(
        packages.PackageRestriction(attr, matcher)
        for attr in ('description', 'longdescription')))

@bind_add_query(
    '--eapi', action='append',
    help='match packages using a given EAPI')
def parse_eapi(value):
    """Value is matched against package EAPI versions."""
    return packages.PackageRestriction(
        'eapi',
        values.StrExactMatch(value))

@bind_add_query(
    '--owns', action='append',
    help='exact match on an owned file/dir')
def parse_owns(value):
    return packages.PackageRestriction(
        'contents',
        values.AnyMatch(values.GetAttrRestriction(
            'location', values.StrExactMatch(value))))

@bind_add_query(
    '--owns-re', action='append',
    help='like "owns" but using a regexp for matching')
def parse_ownsre(value):
    """Value is a regexp matched against the string form of an fs object.

    This means the object kind is prepended to the path the regexp has
    to match.
    """
    return packages.PackageRestriction(
        'contents',
        values.AnyMatch(values.GetAttrRestriction(
            'location', values.StrRegex(value))))

@bind_add_query(
    '--maintainer', action='append',
    help='comma-separated list of regexes to search for maintainers')
def parse_maintainer(value):
    """
    Case insensitive Regex match on the combined 'name <email>' bit of
    metadata.xml's maintainer data.
    """
    if value:
        return packages.PackageRestriction(
            'maintainers',
            values.AnyMatch(values.UnicodeConversion(
            values.StrRegex(value.lower(), case_sensitive=False))))
    else:
        # empty string matches packages without a maintainer
        return packages.PackageRestriction(
            'maintainers',
            values.EqualityMatch(()))

@bind_add_query(
    '--maintainer-name', action='append',
    help='comma-separated list of maintainer name regexes to search for')
def parse_maintainer_name(value):
    """
    Case insensitive Regex match on the name bit of metadata.xml's
    maintainer data.
    """
    return packages.PackageRestriction(
        'maintainers',
        values.AnyMatch(values.GetAttrRestriction(
            'name', values.StrRegex(value.lower(), case_sensitive=False))))

@bind_add_query(
    '--maintainer-email', action='append',
    help='comma-separated list of maintainer email regexes to search for')
def parse_maintainer_email(value):
    """
    Case insensitive Regex match on the email bit of metadata.xml's
    maintainer data.
    """
    return packages.PackageRestriction(
        'maintainers',
        values.AnyMatch(values.GetAttrRestriction(
            'email', values.StrRegex(value.lower(), case_sensitive=False))))

@bind_add_query(
    '--environment', action='append',
    help='regexp search in environment.bz2')
def parse_envmatch(value):
    """Apply a regexp to the environment."""
    return packages.PackageRestriction(
        'environment', DataSourceRestriction(values.AnyMatch(
            values.StrRegex(value))))

# note the type=str; this is to suppress the default
# fallback of using match parsing.
add_query(
    '--pkgset', action=commandline.StoreConfigObject,
    nargs=1, type=str, priority=35, config_type='pkgset',
    help='find packages that match the given package set (world for example)')

# add a fallback if no restrictions are specified.
_query_items.append('_fallback_all')
def _add_all_if_needed(namespace, attr):
    val = [packages.AlwaysTrue]
    for query_attr in _query_items:
        if getattr(namespace, f'_{query_attr}', None):
            val = None
            break
    setattr(namespace, attr, val)

@bind_add_query(
    '-u', '--upgrade', action='store_true',
    metavar=None, type=None, bind='final_converter',
    help='match installed packages without best slotted version')
def pkg_upgrade(_value, namespace):
    pkgs = []
    for pkg in namespace.domain.all_installed_repos:
        matches = sorted(namespace.domain.all_source_repos.match(pkg.slotted_atom))
        if matches and matches[-1] != pkg:
            pkgs.append(matches[-1].versioned_atom)
    return packages.OrRestriction(*pkgs)

argparser.set_defaults(
    _fallback_all=arghparse.DelayedValue(_add_all_if_needed, priority=89))
argparser.set_defaults(
    query=commandline.BooleanQuery(_query_items, klass_type='and', priority=90))

output = argparser.add_argument_group('output options')
output.add_argument(
    '-1', '--first', action='store_true',
    help='stop when first match is found')
output.add_argument(
    '-a', '--atom', action=arghparse.Expansion,
    subst=(('--cpv',),),
    help='print =cat/pkg-3 instead of cat/pkg-3.',
    docs="""
        Output valid package atoms, e.g. =cat/pkg-3 instead of cat/pkg-3.

        Note that this option implies --cpv and has no effect if used with
        --no-version.
    """)
output.add_argument(
    '--cpv', action='store_true',
    help='print the category/package-version',
    docs="""
        Display output in the format of 'category/package-version' which is
        done by default, this option forces the output format if another output
        option (such as --contents) alters it.
    """)
output.add_argument(
    '-R', action='store_true', dest='display_repo',
    help='print the repo of the package')
output.add_argument(
    '--slot', action='store_true', dest='display_slot',
    help='print the slot of the package')

output_mux = output.add_mutually_exclusive_group()
output_mux.add_argument(
    '-n', '--no-version', action='store_true',
    dest='noversion',
    help='collapse multiple matching versions together')
output_mux.add_argument(
    '--min', action='store_true',
    help='show only the lowest version for each package')
output_mux.add_argument(
    '--max', action='store_true',
    help='show only the highest version for each package')
del output_mux

output.add_argument(
    '--blame', action=arghparse.Expansion,
    subst=(("--attr", "maintainers"),),
    help='shorthand for --attr maintainers')
output.add_argument(
    '--size', action='store_true',
    help='display size of all files owned by the package')
output.add_argument(
    '--contents', action='store_true',
    help='list files owned by the package')
output.add_argument(
    '--highlight-dep', action='append',
    type=atom.atom, default=[],
    help='highlight dependencies matching this atom')
output.add_argument(
    '--print-revdep', action='append',
    type=atom.atom, default=[],
    help='print what condition(s) trigger a dep')

output.add_argument(
    '--attr', action='append', choices=printable_attrs,
    metavar='attribute', default=[],
    help="print this attribute's value (can be specified more than once)",
    docs=f"""
        Print the given attribute's value. This option can be specified
        multiple times.

        Valid attributes: {', '.join(printable_attrs)}
    """)
output.add_argument(
    '--force-attr', action='append', dest='attr',
    metavar='attribute', default=[],
    help='like --attr but accepts any string as '
         'attribute name instead of only explicitly '
         'supported names')
one_attr_mux = output.add_mutually_exclusive_group()
one_attr_mux.add_argument(
    '--one-attr', choices=printable_attrs,
    metavar='attribute',
    help="print one attribute, suppresses other output")
one_attr_mux.add_argument(
    '--force-one-attr',
    metavar='attribute',
    help='like --one-attr but accepts any string as '
         'attribute name instead of only explicitly '
         'supported names')
del one_attr_mux


def get_pkg_attr(pkg, attr, fallback=None):
    if attr[0:4] == 'raw_':
        pkg = getattr(pkg, '_raw_pkg', pkg)
        attr = attr[4:]
    return getattr(pkg, attr, fallback)


@argparser.bind_final_check
def _validate_args(parser, namespace):
    if namespace.noversion:
        if namespace.contents:
            parser.error('both --no-version and --contents does not make sense')
        if namespace.min or namespace.max:
            parser.error('--no-version with --min or --max does not make sense')
        if namespace.print_revdep:
            parser.error('--print-revdep with --no-version does not make sense')

    if namespace.one_attr and namespace.print_revdep:
        parser.error('--print-revdep with --force-one-attr or --one-attr does not make sense')

    def process_attrs(sequence):
        for attr in sequence:
            if attr == 'all':
                i = [x for x in printable_attrs if x != 'all']
            elif attr == 'allmetadata':
                i = process_attrs(metadata_attrs)
            elif attr == 'alldepends':
                i = ['bdepend', 'depend', 'rdepend', 'pdepend']
            elif attr == 'raw_alldepends':
                i = ['raw_bdepend', 'raw_depend', 'raw_rdepend', 'raw_pdepend']
            else:
                i = [attr]
            for attr in i:
                yield attr

    attrs = ['repo', 'description', 'homepage', 'license'] if namespace.verbosity > 0 else []
    attrs.extend(process_attrs(namespace.attr))

    # finally, uniquify the attrs.
    namespace.attr = list(iter_stable_unique(attrs))


@argparser.bind_main_func
def main(options, out, err):
    """Run a query."""
    if options.debug:
        for repo in options.repos:
            out.write(f'repo: {repo.repo_id}')
        out.write(f'restrict: {options.query}')
        out.write()

    if options.query is None:
        return 0
    for repo in options.repos:
        try:
            for pkgs in pkgutils.groupby_pkg(repo.itermatch(options.query, sorter=sorted)):
                pkgs = list(pkgs)
                if options.noversion:
                    print_packages_noversion(options, out, err, pkgs)
                elif options.min or options.max:
                    if options.min:
                        print_package(options, out, err, min(pkgs))
                    if options.max:
                        print_package(options, out, err, max(pkgs))
                else:
                    for pkg in pkgs:
                        print_package(options, out, err, pkg)
                        if options.first:
                            break
                if options.first:
                    break

        except KeyboardInterrupt:
            raise
        except Exception as e:
            if isinstance(e, IOError) and e.errno == errno.EPIPE:
                # swallow it; receiving end shutdown early.
                return
            # force a newline for error msg or traceback output
            err.write()
            raise
