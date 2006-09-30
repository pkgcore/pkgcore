# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2
# Based on pquery by Brian Harring <ferringb@gmail.com>


"""Extract information from repositories."""


import optparse

from pkgcore.util import (
    commandline, repo_utils, parserestrict, packages as pkgutils, formatters)
from pkgcore.restrictions import packages, values
from pkgcore.ebuild import conditionals, atom


# To add a new restriction you have to do the following:
# - add a parse function for it here.
# - add the parse function to the PARSE_FUNCS dict.
# - add an optparse option using the name you used in the dict as
#   both the typename and the long option name.

def parse_revdep(value):
    """Value should be an atom, packages with deps intersecting that match."""
    try:
        targetatom = atom.atom(value)
    except atom.MalformedAtom, e:
        raise parserestrict.ParseError(str(e))
    val_restrict = values.FlatteningRestriction(
        atom.atom,
        values.AnyMatch(values.FunctionRestriction(targetatom.intersects)))
    return packages.OrRestriction(finalize=True, *list(
            packages.PackageRestriction(dep, val_restrict)
            for dep in ('depends', 'rdepends', 'post_rdepends')))

def parse_description(value):
    """Value is used as a regexp matching description or longdescription."""
    matcher = values.StrRegex(value, case_sensitive=False)
    return packages.OrRestriction(finalize=True, *list(
            packages.PackageRestriction(attr, matcher)
            for attr in ('description', 'longdescription')))

def parse_ownsre(value):
    """Value is a regexp matched against the string form of an fs object.

    This means the object kind is prepended to the path the regexp has
    to match.
    """
    return packages.PackageRestriction(
        'contents', values.AnyMatch(values.GetAttrRestriction(
                'location', values.StrRegex(value))))


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
        return self.restriction.match(iter(value.get_fileobj())) ^ self.negate


def parse_envmatch(value):
    """Apply a regexp to the environment."""
    return packages.PackageRestriction(
        'environment', DataSourceRestriction(values.AnyMatch(
                values.StrRegex(value))))


def parse_expression(string):
    """Convert a string to a restriction object using pyparsing."""
    # Two reasons to delay this import: we want to deal if it is
    # not there and the import is slow (needs to compile a bunch
    # of regexps).
    try:
        import pyparsing as pyp
    except ImportError:
        raise parserestrict.ParseError('pyparsing is not installed.')

    grammar = getattr(parse_expression, 'grammar', None)
    if grammar is None:

        anystring = pyp.quotedString.copy().setParseAction(pyp.removeQuotes)
        anystring |= pyp.Word(pyp.alphanums + ',')

        def funcall(name, parser):
            """Create a pyparsing expression from a name and parse func."""
            # This function cannot be inlined below: we use its scope to
            # "store" the parser function. If we store the parser function
            # as default argument to the _parse function pyparsing passes
            # different arguments (it detects the number of arguments the
            # function takes).
            result = (pyp.Suppress('%s(' % (name,)) + anystring +
                      pyp.Suppress(')'))
            def _parse(tokens):
                return parser(tokens[0])
            result.setParseAction(_parse)
            return result


        boolcall = pyp.Forward()
        expr = boolcall
        for name, func in PARSE_FUNCS.iteritems():
            expr |= funcall(name, func)

        andcall = (pyp.Suppress(pyp.CaselessLiteral('and') + '(') +
                   pyp.delimitedList(expr) + pyp.Suppress(')'))
        def _parse_and(tokens):
            return packages.AndRestriction(*tokens)
        andcall.setParseAction(_parse_and)

        orcall = (pyp.Suppress(pyp.CaselessLiteral('or') + '(') +
                   pyp.delimitedList(expr) + pyp.Suppress(')'))
        def _parse_or(tokens):
            return packages.OrRestriction(*tokens)
        orcall.setParseAction(_parse_or)

        notcall = (pyp.Suppress(pyp.CaselessLiteral('not') + '(') + expr +
                   pyp.Suppress(')'))
        def _parse_not(tokens):
            restriction = tokens[0]
            restriction.negate = not restriction.negate
            return restriction
        notcall.setParseAction(_parse_not)

        # "Statement seems to have no effect"
        # pylint: disable-msg=W0104
        boolcall << (notcall | andcall | orcall)

        # This forces a match on the entire thing, without it trailing
        # unparsed data is ignored.
        grammar = pyp.stringStart + expr + pyp.stringEnd

        # grammar.validate()

        parse_expression.grammar = grammar

    try:
        return grammar.parseString(string)[0]
    except pyp.ParseException, e:
        raise parserestrict.ParseError(e.msg)


PARSE_FUNCS = {
    'revdep': parse_revdep,
    'description': parse_description,
    'ownsre': parse_ownsre,
    'environment': parse_envmatch,
    'expr': parse_expression,
    }

# This is not just a blind "update" because we really need a config
# option for everything in this dict (so parserestrict growing parsers
# would break us).
for _name in ['match']:
    PARSE_FUNCS[_name] = parserestrict.parse_funcs[_name]

for _name, _attr in [
    ('herd', 'herds'),
    ('license', 'license'),
    ('hasuse', 'iuse'),
    ('maintainer', 'maintainers'),
    ('owns', 'contents'),
    ]:
    PARSE_FUNCS[_name] = parserestrict.comma_separated_containment(_attr)

del _name, _attr


def optparse_type(parsefunc):
    """Wrap a parsefunc shared with the expression-style code for optparse."""
    def _typecheck(option, opt, value):
        try:
            return parsefunc(value)
        except parserestrict.ParseError, e:
            raise optparse.OptionValueError('option %s: %s' % (opt, e))
    return _typecheck


extras = dict((parser_name, optparse_type(parser_func))
              for parser_name, parser_func in PARSE_FUNCS.iteritems())

class Option(optparse.Option):
    """C{optparse.Option} subclass supporting our custom types."""
    TYPES = optparse.Option.TYPES + tuple(extras.keys())
    # Copy the original dict
    TYPE_CHECKER = dict(optparse.Option.TYPE_CHECKER)
    TYPE_CHECKER.update(extras)


class OptionParser(commandline.OptionParser):

    """Option parser with custom option postprocessing and validation."""

    def __init__(self):
        commandline.OptionParser.__init__(
            self, description=__doc__, option_class=Option)

        self.add_option('--domain', action='store',
                        help='domain name to use (default used if omitted).')
        self.add_option('--early-out', action='store_true', dest='earlyout',
                        help='stop when first match is found.')
        self.add_option('--no-version', '-n', action='store_true',
                        dest='noversion',
                        help='collapse multiple matching versions together')
        self.add_option('--min', action='store_true',
                        help='show only the lowest version for each package.')
        self.add_option('--max', action='store_true',
                        help='show only the highest version for each package.')

        repo = self.add_option_group('Source repo')
        repo.add_option('--raw', action='store_true',
                        help='Without this switch your configuration affects '
                        'what packages are visible (through masking) and what '
                        'USE flags are applied to depends and fetchables. '
                        "With this switch your configuration values aren't "
                        'used and you see the "raw" repository data.')
        repo.add_option(
            '--virtuals', action='store', choices=('only', 'disable'),
            help='arg "only" for only matching virtuals, "disable" to not '
            'match virtuals at all. Default is to match everything.')
        repo.add_option('--vdb', action='store_true',
                        help='match only vdb (installed) packages.')
        repo.add_option('--all-repos', action='store_true',
                        help='search all repos, vdb included')
        restrict = self.add_option_group(
            'Package matching',
            'Each option specifies a restriction packages must match.  '
            'Specifying the same option twice means "or" unless stated '
            'otherwise. Specifying multiple types of restrictions means "and" '
            'unless stated otherwise.')
        restrict.add_option(
            '--match', '-m', action='append', type='match',
            help='Glob-like match on category/package-version.')
        restrict.add_option('--has-use', action='append', type='hasuse',
                            dest='hasuse',
                            help='Exact string match on a USE flag.')
        restrict.add_option('--revdep', action='append', type='revdep',
                            help='Dependency on an atom.')
        restrict.add_option('--description', '-S', action='append',
            type='description',
            help='regexp search on description and longdescription.')
        restrict.add_option('--herd', action='append', type='herd',
                            help='exact match on a herd.')
        restrict.add_option('--license', action='append', type='license',
                            help='exact match on a license.')
        restrict.add_option('--owns', action='append', type='owns',
                            help='exact match on an owned file/dir.')
        restrict.add_option(
            '--owns-re', action='append', type='ownsre', dest='ownsre',
            help='like "owns" but using a regexp for matching.')
        restrict.add_option('--maintainer', action='append', type='maintainer',
                            help='comma-separated list of maintainers.')
        restrict.add_option(
            '--environment', action='append', type='environment',
            help='regexp search in environment.bz2.')
        restrict.add_option(
            '--expr', action='append', type='expr',
            help='Boolean combinations of other restrictions, like '
            '\'and(not(herd("python")), match("dev-python/*"))\'. '
            'WARNING: currently not completely reliable.')
        # XXX fix the negate stuff and remove that warning.

        printable_attrs = ('rdepends', 'depends', 'post_rdepends', 'provides',
                           'use', 'iuse', 'description', 'longdescription',
                           'herds', 'license', 'uris', 'files',
                           'slot', 'maintainers', 'restrict', 'repo',
                           'alldepends', 'path', 'environment', 'keywords',
                           'homepage')

        output = self.add_option_group('Output formatting')
        output.add_option(
            '--cpv', action='store_true',
            help='Print the category/package-version. This is done '
            'by default, this option re-enables this if another '
            'output option (like --contents) disabled it.')
        output.add_option('--atom', '-a', action='store_true',
                          help='print =cat/pkg-3 instead of cat/pkg-3. '
                          'Implies --cpv, has no effect with --no-version')
        output.add_option('--attr', action='append', choices=printable_attrs,
            help="Print this attribute's value (can be specified more than "
            "once).  --attr=help will get you the list of valid attrs.")
        output.add_option('--one-attr', choices=printable_attrs,
                          help="Print one attribute. Suppresses other output.")
        output.add_option('--force-attr', action='append', dest='attr',
                          help='Like --attr but accepts any string as '
                          'attribute name instead of only explicitly '
                          'supported names.')
        output.add_option('--force-one-attr',
                          help='Like --oneattr but accepts any string as '
                          'attribute name instead of only explicitly '
                          'supported names.')
        output.add_option(
            '--contents', action='store_true',
            help='list files owned by the package. Implies --vdb.')
        output.add_option('--verbose', '-v', action='store_true',
                          help='human-readable multi-line output per package')

    def check_values(self, vals, args):
        """Sanity check and postprocess after parsing."""
        vals, args = commandline.OptionParser.check_values(self, vals, args)
        if vals.contents or vals.owns or vals.ownsre:
            vals.vdb = True

        if vals.atom:
            vals.cpv = True

        if vals.noversion and vals.contents:
            self.error('both --no-version and --contents does not make sense.')

        if vals.noversion and (vals.min or vals.max):
            self.error('--no-version with --min or --max does not make sense.')

        if 'alldepends' in vals.attr:
            vals.attr.remove('alldepends')
            vals.attr.extend(['depends', 'rdepends', 'post_rdepends'])

        if vals.verbose:
            vals.attr.insert(0, 'homepage')
            vals.attr.insert(0, 'description')

        if vals.force_one_attr:
            if vals.one_attr:
                self.error(
                    '--one-attr and --force-one-attr are mutually exclusive.')
            vals.one_attr = vals.force_one_attr

        return vals, args


def stringify_attr(config, pkg, attr):
    """Grab a package attr and convert it to a string."""
    # config is currently unused but may affect display in the future.
    if attr in ('files', 'uris'):
        data = getattr(pkg, 'fetchables', None)
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
        use = set(getattr(pkg, 'use', ()))
        iuse = set(getattr(pkg, 'iuse', ()))
        result = sorted(iuse & use) + sorted('-' + val for val in (iuse - use))
        return ' '.join(result)

    # TODO: is a missing or None attr an error?
    value = getattr(pkg, attr, None)
    if value is None:
        return 'MISSING'

    if attr in ('herds', 'iuse', 'maintainers', 'restrict', 'keywords'):
        return ' '.join(sorted(value))
    if attr == 'environment':
        return ''.join(value.get_fileobj())
    return str(value)


def print_package(options, out, err, pkg):
    """Print a package."""
    if options.verbose:
        green = out.fg('green')
        out.write(out.bold, green, ' * ', out.fg(), pkg.cpvstr)
        out.wrap = True
        out.later_prefix = ['                  ']
        for attr in options.attr:
            out.write(green, '     %s: ' % (attr,), out.fg(),
                      stringify_attr(options, pkg, attr))
        out.write()
        out.later_prefix = []
        out.wrap = False
    elif options.one_attr:
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
        # If we printed anything at all print the newline now
        out.autoline = True
        if printed_something:
            out.write()

    if options.contents:
        for location in sorted(obj.location
                               for obj in getattr(pkg, 'contents', ())):
            out.write(location)

def print_packages_noversion(options, out, err, pkgs, vdbs):
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
                pkg.fullver for vdb in vdbs
                for pkg in vdb.itermatch(pkgs[0].unversioned_atom))
            out.write(green, '     installed: ', out.fg(), ' '.join(versions))
        for attr in options.attr:
            out.write(green, '     %s: ' % (attr,), out.fg(),
                      stringify_attr(options, pkgs[-1], attr))
        out.write()
        out.wrap = False
        out.later_prefix = []
    elif options.one_attr:
        out.write(stringify_attr(options, pkgs[-1], options.oneattr))
    else:
        out.autoline = False
        out.write(pkgs[0].key)
        for attr in options.attr:
            out.write(' %s="%s"' % (attr, stringify_attr(options, pkgs[-1],
                                                         attr)))
        out.autoline = True
        out.write()


def main(config, options, out, err):
    """Do stuff.

    @param config: pkgcore config central.
    @param options: optparse option values.
    @type  out: L{pkgcore.util.formatters.Formatter} instance.
    @param out: stream to output on.
    @type  err: file-like object
    @param err: stream for errors (usually C{sys.stderr})

    @returns: the exit code.
    """
    # Get a domain object.
    if options.domain:
        try:
            domain = config.domain[options.domain]
        except KeyError:
            err.write('domain %s not found\n' % (options.domain,))
            err.write('Valid domains: %s\n' %
                      (', '.join(config.domain.keys()),))
            return 1
    else:
        domain = config.get_default('domain')
        if domain is None:
            err.write(
                'No default domain found, fix your configuration '
                'or pass --domain\n')
            err.write('Valid domains: %s\n' %
                      (', '.join(config.domain.keys()),))
            return 1

    # Get the vdb if we need it.
    if options.verbose and options.noversion:
        vdbs = domain.vdb
    else:
        vdbs = None
    # Get repo(s) to operate on.
    if options.vdb:
        repos = domain.vdb
    elif options.all_repos:
        repos = domain.repos + domain.vdb
    else:
        repos = domain.repos
    if options.raw or options.virtuals:
        repos = repo_utils.get_raw_repos(repos)
    if options.virtuals:
        repos = repo_utils.get_virtual_repos(repos, options.virtuals == 'only')

    # Build up a restriction.
    restrict = []
    for attr in PARSE_FUNCS.keys():
        val = getattr(options, attr)
        if len(val) == 1:
            # Omit the boolean.
            restrict.append(val[0])
        elif val:
            restrict.append(packages.OrRestriction(finalize=True, *val))

    if not restrict:
        # Match everything in the repo.
        restrict = packages.AlwaysTrue
    elif len(restrict) == 1:
        # Single restriction, omit the AndRestriction for a bit of speed
        restrict = restrict[0]
    else:
        # "And" them all together
        restrict = packages.AndRestriction(finalize=True, *restrict)

    if options.debug:
        for repo in repos:
            out.write('repo: %r' % (repo,))
        out.write('restrict: %r' % (restrict,))
        out.write()

    # Run the query
    for repo in repos:
        try:
            for pkgs in pkgutils.groupby_pkg(
                repo.itermatch(restrict, sorter=sorted)):
                pkgs = list(pkgs)
                if options.noversion:
                    print_packages_noversion(options, out, err, pkgs, vdbs)
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

        except (KeyboardInterrupt, formatters.StreamClosed):
            raise
        except Exception:
            err.write('caught an exception!\n')
            err.write('repo: %r\n' % (repo,))
            err.write('restrict: %r\n' % (restrict,))
            raise
