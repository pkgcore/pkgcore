# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006-2007 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Extract information from repositories."""

from pkgcore.restrictions import packages, values, boolean, restriction
from pkgcore.ebuild import conditionals, atom
from pkgcore.util import (
    commandline, repo_utils, parserestrict, packages as pkgutils)
from snakeoil.currying import partial
from snakeoil.formatters import decorate_forced_wrapping
from snakeoil.demandload import demandload
demandload(globals(),
    're',
    'errno',
    'snakeoil.lists:iter_stable_unique',
    'pkgcore.fs:fs@fs_module,contents@contents_module',
)


def mk_strregex(value, **kwds):
    try:
        return values.StrRegex(value, **kwds)
    except re.error, e:
        raise ValueError("invalid regex: %r, %s" % (value, e))


class DataSourceRestriction(values.base):

    """Turn a data_source into a line iterator and apply a restriction."""

    def __init__(self, childrestriction, **kwargs):
        values.base.__init__(self, **kwargs)
        self.restriction = childrestriction

    def __str__(self):
        return 'DataSourceRestriction: %s negate=%s' % (
            self.restriction, self.negate)

    def __repr__(self):
        if self.negate:
            string = '<%s restriction=%r negate @%#8x>'
        else:
            string = '<%s restriction=%r @%#8x>'
        return string % (self.__class__.__name__, self.restriction, id(self))

    def match(self, value):
        return self.restriction.match(iter(value.text_fileobj())) ^ self.negate

    __hash__ = object.__hash__


dep_attrs = ['rdepends', 'depends', 'post_rdepends']
metadata_attrs = dep_attrs
dep_attrs += list('raw_%s' % x for x in dep_attrs)
dep_formatted_attrs = dep_attrs + ['restrict']
dep_formatted_attrs = frozenset(dep_attrs + ['restrict'])
dep_attrs = tuple(sorted(dep_attrs))

metadata_attrs += [
    'provides', 'use', 'iuse', 'description', 'license', 'fetchables',
    'slot', 'subslot', 'keywords', 'homepage', 'eapi', 'properties', 'defined_phases',
    'restrict', 'required_use', 'inherited',]
metadata_attrs = tuple(sorted(metadata_attrs))

printable_attrs = tuple(dep_formatted_attrs) + metadata_attrs
printable_attrs += (
    'alldepends', 'raw_alldepends',
    'longdescription', 'herds', 'uris', 'files', 'category', 'package',
    'maintainers', 'repo', 'source_repository', 'path', 'version',
    'revision', 'fullver', 'environment',
    'chost', 'cbuild', 'ctarget',
    'all', 'allmetadata',
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
                return ' '.join(node.uri or ())
        return conditionals.stringify_boolean(data, _format)

    if attr == 'use':
        # Combine a list of all enabled (including irrelevant) and all
        # available flags into a "enabled -disabled" style string.
        use = set(get_pkg_attr(pkg, 'use', ()))
        iuse = set(x.lstrip("-+") for x in get_pkg_attr(pkg, 'iuse', ()))
        result = sorted(iuse & use) + sorted('-' + val for val in (iuse - use))
        return ' '.join(result)

    value = get_pkg_attr(pkg, attr)
    if value is None:
        return 'MISSING'

    if attr in ('herds', 'iuse', 'maintainers', 'properties', 'defined_phases',
        'inherited'):
        return ' '.join(sorted(unicode(v) for v in value))
    if attr == 'longdescription':
        return unicode(value)
    if attr == 'keywords':
        return ' '.join(sorted(value, key=lambda x:x.lstrip("~")))
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
    :returns: The same kind of boolean func should return.
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
                uris = list(node.uri)
                if not uris:
                    return False
                if len(uris) == 1:
                    out.write(uris[0], autoline=False)
                    return False
                out.write('|| (')
                out.first_prefix.append('    ')
                for uri in uris:
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
    if options.verbose:
        green = out.fg('green')
        out.write(out.bold, green, ' * ', out.fg(), pkg.cpvstr)
        out.wrap = True
        out.later_prefix = ['                  ']
        for attr in options.attr:
            out.write(green, '     %s: ' % (attr,), out.fg(), autoline=False)
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
                for key, restricts in depset.find_cond_nodes(
                    depset.restrictions, True):
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
                for key, restricts in depset.node_conds.iteritems():
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
            out.write(pkg.cpvstr, ':', autoline=False)
        out.write(stringify_attr(options, pkg, options.one_attr))
    else:
        printed_something = False
        out.autoline = False
        if (not options.contents) or options.cpv:
            printed_something = True
            if options.atom:
                out.write('=')
            out.write(pkg.cpvstr)
        for attr in options.attr:
            if printed_something:
                out.write(' ')
            printed_something = True
            out.write('%s="%s"' % (attr, stringify_attr(options, pkg, attr)))
        for revdep in options.print_revdep:
            for name in dep_attrs:
                depset = get_pkg_attr(pkg, name)
                if getattr(depset, 'find_cond_nodes', None) is None:
                    # TODO maybe be smarter here? (this code is
                    # triggered by virtuals currently).
                    out.write(' %s on %s' % (name, revdep))
                    continue
                for key, restricts in depset.find_cond_nodes(
                    depset.restrictions, True):
                    if not restricts and key.intersects(revdep):
                        out.write(' %s on %s through %s' % (name, revdep, key))
                for key, restricts in depset.node_conds.iteritems():
                    if key.intersects(revdep):
                        out.write(' %s on %s through %s if USE %s,' % (
                                name, revdep, key, ' or '.join(
                                    str(r) for r in restricts)))
        # If we printed anything at all print the newline now
        out.autoline = True
        if printed_something:
            out.write()

    if options.contents:
        for location in sorted(obj.location
            for obj in get_pkg_attr(pkg, 'contents', ())):
            out.write(location)

def print_packages_noversion(options, out, err, pkgs):
    """Print a summary of all versions for a single package."""
    if options.verbose:
        green = out.fg('green')
        out.write(out.bold, green, ' * ', out.fg(), pkgs[0].key)
        out.wrap = True
        out.later_prefix = ['                  ']
        versions = ' '.join(pkg.fullver for pkg in sorted(pkgs))
        out.write(green, '     versions: ', out.fg(), versions)
        # If we are already matching on all repos we do not need to duplicate.
        if not (options.vdb or options.all_repos):
            versions = sorted(
                pkg.fullver for vdb in options.vdbs
                for pkg in vdb.itermatch(pkgs[0].unversioned_atom))
            out.write(green, '     installed: ', out.fg(), ' '.join(versions))
        for attr in options.attr:
            out.write(green, '     %s: ' % (attr,), out.fg(),
                      stringify_attr(options, pkgs[-1], attr))
        out.write()
        out.wrap = False
        out.later_prefix = []
    elif options.one_attr:
        if options.atom:
            out.write('=', autoline=False)
        if options.atom or options.cpv:
            out.write(pkgs[0].key, ':', autoline=False)
        out.write(stringify_attr(options, pkgs[-1], options.one_attr))
    else:
        out.autoline = False
        out.write(pkgs[0].key)
        for attr in options.attr:
            out.write(' %s="%s"' % (attr, stringify_attr(options, pkgs[-1],
                                                         attr)))
        out.autoline = True
        out.write()


# note the usage of priorities throughout this argparse setup;
# priority 0 (commandline sets this):
#  basically, sort the config first (additions/removals/etc),
# priority 30:
#   sort the repositories
# priority 50:
#  sort the query args individually (potentially accessing the config) along
#  or lines for each (thus multiple revdep args are or'd together)
# priority 90:
#  finally generate a final query object, a boolean and of all previous
#  queries.
# priority 100:
#  default priority for DelayedValue; anything else is setup then.

argparser = commandline.mk_argparser(domain=True,
    description="pkgcore query interface")

repo_group = argparser.add_argument_group('Repository matching options',
    'options controlling which repositories to inspect.')
repo_group.add_argument('--raw', action='store_true', default=False,
    help="With this switch enabled, no configuration is used, and no filtering "
         " is done.  This means you see the raw dependencies, rather than the "
         "dependencies rendered via your USE configuration.  Primarily useful "
         "for people who need to look under the hood- ebuild devs, PM tool "
         "authors, etc.  Note this option ignores --domain if is specified.")
repo_group.add_argument('--no-filters', action='store_true', default=False,
    help="With this option enabled, all license filtering, visibility filtering"
         " (ACCEPT_KEYWORDS, package masking, etc) is turned off.")
repo_group.add_argument('--virtuals', action='store', choices=('only', 'disable'),
    help='arg "only" for only matching virtuals, "disable" to not match '
        'virtuals at all. Default is to match everything.')

repo_mux = repo_group.add_mutually_exclusive_group()

class RawAwareStoreRepoObject(commandline.StoreRepoObject):

    """Custom implementation that is aware of the --raw flag."""

    def _get_sections(self, config, namespace):
        if namespace.raw:
            return commandline.StoreConfigObject._get_sections(
                self, config, namespace)
        elif namespace.no_filters:
            return namespace.domain.repos_configured
        return commandline.StoreRepoObject._get_sections(
            self, config, namespace)

repo_mux.add_argument('--repo',
    action=RawAwareStoreRepoObject, priority=29,
    help='repo to use (default from domain if omitted).')
repo_mux.add_argument('--vdb', action='store_true',
    help='match only vdb (installed) packages.')
repo_mux.add_argument('--all-repos', action='store_true',
    help='search all repos, vdb included')

@argparser.bind_delayed_default(30, 'repos')
def setup_repos(namespace, attr):
    # Get the vdb if we need it.  This shouldn't be here...
    if namespace.verbose and namespace.noversion:
        namespace.vdbs = namespace.domain.vdb
    else:
        namespace.vdbs = None

    if namespace.contents or namespace._owns or namespace._owns_re:
        namespace.vdb = True

    # Get repo(s) to operate on.
    if namespace.repo:
        # The store repo machinery handles --raw and --no-filters for
        # us, thus it being the first check.
        repos = [namespace.repo]
    elif namespace.vdb:
        repos = namespace.domain.vdb
    elif namespace.no_filters:
        if namespace.all_repos:
            repos = list(namespace.domain.vdb)
            repos.extend(namespace.domain.repos_configured.itervalues())
        else:
            repos = namespace.domain.repos_configured.values()
    elif namespace.all_repos:
        repos = namespace.domain.repos + namespace.domain.vdb
    else:
        repos = namespace.domain.repos

    if namespace.raw or namespace.virtuals:
        repos = repo_utils.get_raw_repos(repos)
    if namespace.virtuals:
        repos = repo_utils.get_virtual_repos(
            repos, namespace.virtuals == 'only')
    setattr(namespace, attr, repos)

query = argparser.add_argument_group('Package matching options',
    'Each option specifies a restriction packages must match.  '
    'Specifying the same option twice means "or" unless stated '
    'otherwise. Specifying multiple types of restrictions means "and" '
    'unless stated otherwise.')

# for queries, use add_query always; this has the bookkeeping
# necessary to ensure the sub-query gets bound into the
# finalized query
_query_items = []
def add_query(*args, **kwds):
    _query_items.append(kwds["dest"])
    kwds.setdefault('final_priority', 50)
    kwds.setdefault('default', [])
    if not kwds.pop('suppress_nargs', False):
        if kwds.get('action', None) != 'append':
            kwds.setdefault('nargs', 1)
    commandline.make_query(query, *args, **kwds)

def bind_add_query(*args, **kwds):
    def f(functor):
        kwds[kwds.pop('bind', 'type')] = functor
        add_query(*args, **kwds)
        return functor
    return f

add_query(nargs='*', dest='matches',
    help="extended atom matching of pkgs")
add_query('--all', action='append_const', dest='all',
    const=packages.AlwaysTrue, type=None, suppress_nargs=True,
    help='Match all packages (equivalent to "pquery *").  '
        'If no query options are specified, this option is enabled.')
add_query('--has-use', action='append', dest='has_use',
    type=parserestrict.comma_separated_containment('iuse'),
    help='Exact string match on a USE flag.')
add_query('--license', action='append', dest='license',
    type=parserestrict.comma_separated_containment('license'),
    help='exact match on a license.')
add_query('--herd', action='append', dest='herd',
    type=parserestrict.comma_separated_containment('herds'),
    help='exact match on a herd.')

query.add_argument('--revdep', nargs=1,
    action=commandline.Expansion,
    subst=(('--restrict-revdep', '%(0)s'), ('--print-revdep', '%(0)s')),
    help='shorthand for --restrict-revdep atom --print-revdep atom. '
        '--print-revdep is slow, use just --restrict-revdep if you just '
        'need a list.')

query.add_argument('--revdep-pkgs', nargs=1,
    action=commandline.Expansion,
    subst=(('--restrict-revdep-pkgs', '%(0)s'), ('--print-revdep', '%(0)s')),
    help='shorthand for --restrict-revdep-pkgs atom '
        '--print-revdep atom. --print-revdep is slow, use just '
        '--restrict-revdep if you just need a list.')

@bind_add_query('--restrict-revdep', action='append',
    default=[], dest='restrict_revdep',
    help='Dependency on an atom.')
def parse_revdep(value):
    """Value should be an atom, packages with deps intersecting that match."""
    try:
        targetatom = atom.atom(value)
    except atom.MalformedAtom, e:
        raise parserestrict.ParseError(str(e))
    val_restrict = values.FlatteningRestriction(
        atom.atom,
        values.AnyMatch(values.FunctionRestriction(targetatom.intersects)))
    return packages.OrRestriction(*list(
            packages.PackageRestriction(dep, val_restrict)
            for dep in ('depends', 'rdepends', 'post_rdepends')))

def _revdep_pkgs_match(pkgs, value):
    return any(value.match(pkg) for pkg in pkgs)

@bind_add_query('--restrict-revdep-pkgs', action='append', type=atom.atom,
    default=[], dest='restrict_revdep_pkgs',
    bind='final_converter',
    help='Dependency on pkgs that match a specific atom.')
def revdep_pkgs_finalize(sequence, namespace):
    if not sequence:
        return []
    l = []
    for atom_inst in sequence:
        for repo in namespace.repos:
            l.extend(repo.itermatch(atom_inst))
    # have our pkgs; now build the restrict.
    any_restrict = values.AnyMatch(values.FunctionRestriction(
            partial(_revdep_pkgs_match, tuple(l))))
    r = values.FlatteningRestriction(atom.atom, any_restrict)
    return list(packages.PackageRestriction(dep, r)
        for dep in ('depends', 'rdepends', 'post_rdepends'))

@bind_add_query('--description', '-S', action='append', dest='description',
    help='regexp search on description and longdescription.')
def parse_description(value):
    """Value is used as a regexp matching description or longdescription."""
    matcher = mk_strregex(value, case_sensitive=False)
    return packages.OrRestriction(*list(
            packages.PackageRestriction(attr, matcher)
            for attr in ('description', 'longdescription')))

@bind_add_query('--owns', action='append', dest='owns',
    help='exact match on an owned file/dir.')
def parse_owns(value):
    "Value is a comma delimited set of paths to search contents for"
    # yes it would be easier to do this without using parserestrict-
    # we use defer to using it for the sake of a common parsing
    # exposed to the commandline however.
    # the problem here is we don't want to trigger fs* module loadup
    # unless needed- hence this function.
    parser = parserestrict.comma_separated_containment('contents',
        values_kls=contents_module.contentsSet,
        token_kls=partial(fs_module.fsBase, strict=False))
    return parser(value)

@bind_add_query('--owns-re', action='append', dest='owns_re',
    help='like "owns" but using a regexp for matching.')
def parse_ownsre(value):
    """Value is a regexp matched against the string form of an fs object.

    This means the object kind is prepended to the path the regexp has
    to match.
    """
    return packages.PackageRestriction('contents',
        values.AnyMatch(values.GetAttrRestriction(
        'location', mk_strregex(value))))

@bind_add_query('--maintainer', action='append', dest='maintainer',
    help='comma-separated list of regexes to search for '
        'maintainers.')
def parse_maintainer(value):
    """
    Case insensitive Regex match on the combined 'name <email>' bit of
    metadata.xml's maintainer data.
    """
    return packages.PackageRestriction('maintainers',
        values.AnyMatch(values.UnicodeConversion(
        mk_strregex(value.lower(), case_sensitive=False))))

@bind_add_query('--maintainer-name', action='append', dest='maintainer_name',
    help='comma-separated list of maintainer name regexes to search for.')
def parse_maintainer_name(value):
    """
    Case insensitive Regex match on the name bit of metadata.xml's
    maintainer data.
    """
    return packages.PackageRestriction('maintainers',
        values.AnyMatch(values.GetAttrRestriction(
        'name', mk_strregex(value.lower(), case_sensitive=False))))

@bind_add_query('--maintainer-email', action='append', dest='maintainer_email',
    help='comma-separated list of maintainer email regexes to search for.')
def parse_maintainer_email(value):
    """
    Case insensitive Regex match on the email bit of metadata.xml's
    maintainer data.
    """
    return packages.PackageRestriction(
        'maintainers', values.AnyMatch(values.GetAttrRestriction(
                'email', mk_strregex(value.lower(),
                case_sensitive=False))))

@bind_add_query('--environment', action='append', dest='environment',
    help='regexp search in environment.bz2.')
def parse_envmatch(value):
    """Apply a regexp to the environment."""
    return packages.PackageRestriction(
        'environment', DataSourceRestriction(values.AnyMatch(
                mk_strregex(value))))

# note the type=str; this is to suppress the default
# fallback of using match parsing.
add_query('--pkgset', dest='pkgset',
    action=commandline.StoreConfigObject,
    type=str,
    priority=35,
    config_type='pkgset',
    help='find packages that match the given package set (world for example).')

# add a fallback if no restrictions are specified.
_query_items.append('_fallback_all')
def _add_all_if_needed(namespace, attr):
    val = [packages.AlwaysTrue]
    for query_attr in _query_items:
        if getattr(namespace, '_%s' % (query_attr,), None):
            val = None
            break
    setattr(namespace, attr, val)

argparser.set_defaults(_fallback_all=
    commandline.DelayedValue(_add_all_if_needed, priority=89))

argparser.set_defaults(query=
    commandline.BooleanQuery(_query_items, klass_type='and',
        priority=90))


output = argparser.add_argument_group('Output formatting')

output.add_argument('--early-out', action='store_true', dest='earlyout',
    help='stop when first match is found.')
output_mux = output.add_mutually_exclusive_group()
output_mux.add_argument('--no-version', '-n', action='store_true',
    dest='noversion',
    help='collapse multiple matching versions together')
output_mux.add_argument('--min', action='store_true',
    help='show only the lowest version for each package.')
output_mux.add_argument('--max', action='store_true',
    help='show only the highest version for each package.')
del output_mux
output.add_argument('--cpv', action='store_true',
    help='Print the category/package-version. This is done '
    'by default, this option re-enables this if another '
    'output option (like --contents) disabled it.')
output.add_argument('--atom', '-a', action=commandline.Expansion,
    subst=(('--cpv',),), nargs=0,
    help='print =cat/pkg-3 instead of cat/pkg-3. '
        'Implies --cpv, has no effect with --no-version')
output.add_argument('--attr', action='append', choices=printable_attrs,
    metavar='attribute', default=[],
    help="Print this attribute's value (can be specified more than "
    "once).  --attr=help will get you the list of valid attrs.")
output.add_argument('--force-attr', action='append', dest='attr',
    metavar='attribute', default=[],
    help='Like --attr but accepts any string as '
    'attribute name instead of only explicitly '
    'supported names.')
one_attr_mux = output.add_mutually_exclusive_group()
one_attr_mux.add_argument('--one-attr', choices=printable_attrs,
    metavar='attribute',
    help="Print one attribute. Suppresses other output.")
one_attr_mux.add_argument('--force-one-attr',
    metavar='attribute',
    help='Like --one-attr but accepts any string as '
    'attribute name instead of only explicitly '
    'supported names.')
del one_attr_mux
output.add_argument('--contents', action='store_true',
    help='list files owned by the package. Implies --vdb.')
output.add_argument('--verbose', '-v', action='store_true',
    help='human-readable multi-line output per package')
output.add_argument('--highlight-dep', action='append',
    type=atom.atom, default=[],
    help='highlight dependencies matching this atom')
output.add_argument('--blame', action=commandline.Expansion, nargs=0,
    subst=(("--attr", "maintainers"), ("--attr", "herds")),
    help='shorthand for --attr maintainers --attr herds')
output.add_argument('--print-revdep', action='append',
    type=atom.atom, default=[],
    help='print what condition(s) trigger a dep.')


def get_pkg_attr(pkg, attr, fallback=None):
    if attr[0:4] == 'raw_':
        pkg = getattr(pkg, '_raw_pkg', pkg)
        attr = attr[4:]
    return getattr(pkg, attr, fallback)


class _Fail(Exception):
    pass


def mangle_values(vals, err):

    def error_out(*args, **kwds):
        err.write(*args, **kwds)
        raise _Fail()

    if vals.noversion:
        if vals.contents:
            error_out(
                'both --no-version and --contents does not make sense.')
        if vals.min or vals.max:
            error_out(
                '--no-version with --min or --max does not make sense.')
        if vals.print_revdep:
            error_out(
                '--print-revdep with --no-version does not make sense.')

    if vals.one_attr and vals.print_revdep:
        error_out(
            '--print-revdep with --force-one-attr or --one-attr does not '
            'make sense.')

    def process_attrs(sequence):
        for attr in sequence:
            if attr == 'all':
                i = [x for x in printable_attrs if x != 'all']
            elif attr == 'allmetadata':
                i = process_attrs(metadata_attrs)
            elif attr == 'alldepends':
                i = ['depends', 'rdepends', 'post_rdepends']
            elif attr == 'raw_alldepends':
                i = ['raw_depends', 'raw_rdepends', 'raw_post_rdepends']
            else:
                i = [attr]
            for attr in i:
                yield attr


    attrs = ['repo', 'description', 'homepage'] if vals.verbose else []
    attrs.extend(process_attrs(vals.attr))

    # finally, uniquify the attrs.
    vals.attr = list(iter_stable_unique(attrs))

    return vals, ()


@argparser.bind_main_func
def main(options, out, err):
    """Run a query."""

    try:
        mangle_values(options, err)
    except _Fail:
        return -1

    if options.debug:
        for repo in options.repos:
            out.write('repo: %r' % (repo,))
        out.write('restrict: %r' % (options.query,))
        out.write()

    if options.query is None:
        return 0
    for repo in options.repos:
        try:
            for pkgs in pkgutils.groupby_pkg(
                repo.itermatch(options.query, sorter=sorted)):
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
                        if options.earlyout:
                            break
                if options.earlyout:
                    break

        except KeyboardInterrupt:
            raise
        except Exception, e:
            if isinstance(e, IOError) and e.errno == errno.EPIPE:
                # swallow it; receiving end shutdown early.
                return
            err.write('caught an exception!')
            err.write('repo: %r' % (repo,))
            err.write('restrict: %r' % (options.query,))
            raise
