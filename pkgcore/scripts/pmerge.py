# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Mess with the resolver and vdb."""

from time import time

from pkgcore.util import commandline, parserestrict, repo_utils
from pkgcore.ebuild import resolver
from pkgcore.repository import multiplex
from pkgcore.interfaces import observer, format
from pkgcore.ebuild.formatter import formatters
from pkgcore.pkgsets.glsa import KeyedAndRestriction
from pkgcore.ebuild.atom import atom

from snakeoil import lists
from snakeoil.formatters import ObserverFormatter
from snakeoil.compatibility import any

class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, description=__doc__, **kwargs)
        self.add_option('--deep', '-D', action='store_true',
            help='force the resolver to verify already installed dependencies')
        self.add_option('--unmerge', '-C', action='store_true',
            help='unmerge a package')
        self.add_option('--clean', action='store_true',
            help='remove installed packages that are not referenced by any '
            'target packages/sets; defaults to -s world -s system if no targets'
            ' are specified.  Use with *caution*, this option used incorrectly '
            'can render your system unusable.  Implies --deep'),
        self.add_option('--upgrade', '-u', action='store_true',
            help='try to upgrade already installed packages/depencies')
        self.add_option('--set', '-s', action='append',
            help='specify a pkgset to use')
        self.add_option('--ignore-failures', action='store_true',
            help='ignore resolution failures')
        self.add_option('--preload-vdb-state', action='store_true',
            help=\
"""enable preloading of the installed packages database
This causes the resolver to work with a complete graph, thus disallowing
actions that confict with installed packages.  If disabled, it's possible
for the requested action to conflict with already installed dependencies
that aren't involved in the graph of the requested operation""")

        self.add_option('--pretend', '-p', action='store_true',
            help="do the resolution, but don't merge/fetch anything")
        self.add_option('--ask', '-a', action='store_true',
            help="do the resolution, but ask to merge/fetch anything")
        self.add_option('--fetchonly', '-f', action='store_true',
            help="do only the fetch steps of the resolved plan")
        self.add_option('--ignore-cycles', '-i', action='store_true',
            help=\
"""ignore cycles if they're found to be unbreakable;
a depends on b, and b depends on a, with neither built is an example""")

        self.add_option('-B', '--with-built-depends', action='store_true',
            default=False,
            help="whether or not to process build depends for pkgs that "
            "are already built; defaults to ignoring them"),
        self.add_option('--nodeps', action='store_true',
            help='disable dependency resolution')
        self.add_option('--noreplace', action='store_false',
            dest='replace', default=True,
            help="don't reinstall target atoms if they're already installed")
        self.add_option('--usepkg', '-k', action='store_true',
            help="prefer to use binpkgs")
        self.add_option('--usepkgonly', '-K', action='store_true',
            help="use only built packages")
        self.add_option('--empty', '-e', action='store_true',
            help="force rebuilding of all involved packages, using installed "
                "packages only to satisfy building the replacements")
        self.add_option('--force', action='store_true',
                        dest='force',
            help="force merging to a repo, regardless of if it's frozen")
        self.add_option('--oneshot', '-o', '-1', action='store_true',
            default=False,
            help="do not record changes in the world file; if a set is "
                "involved, defaults to forcing oneshot")
        self.add_option(
            '--formatter', '-F', type='choice', choices=formatters.keys(),
            default='portage',
            help='which formatter to output --pretend or --ask output through. '
            'valid values are: %s' % (', '.join(formatters),))
        self.add_option('--verbose', '-v', action='store_true',
            help="be more verbose about the buildplan. Currently only "
            'supported by the portage formatter')
        self.add_option('--quiet', '-q', action='store_true',
            help="be quieter about the buildplan. "
            "*Not* the same as omitting verbose")

    def check_values(self, options, args):
        options, args = commandline.OptionParser.check_values(
            self, options, args)
        options.targets = args

        if options.unmerge:
            if options.set:
                self.error("Using sets with -C probably isn't wise, aborting")
            if options.upgrade:
                self.error("Cannot upgrade and unmerge simultaneously")
            if not options.targets:
                self.error("You must provide at least one atom")
            if options.clean:
                self.error("Cannot use -C with --clean")
        if options.clean:
            if options.set or options.targets:
                self.error("--clean currently has set/targets disabled; in "
                    "other words, accepts no args")
            options.set = ['world', 'system']
            options.deep = True
            if options.usepkgonly or options.usepkg:
                self.error(
                    '--usepkg and --usepkgonly cannot be used with --clean')
        elif options.usepkgonly and options.usepkg:
            self.error('--usepkg is redundant when --usepkgonly is used')
        if options.set:
            options.replace = False
        if not options.targets and not options.set:
            self.error('Need at least one atom/set')
        return options, ()

class AmbiguousQuery(parserestrict.ParseError):
    def __init__(self, token, keys):
        parserestrict.ParseError.__init__(
            self, '%s: multiple matches (%s)' % (token, ', '.join(keys)))
        self.token = token
        self.keys = keys

class NoMatches(parserestrict.ParseError):
    def __init__(self, token):
        parserestrict.ParseError.__init__(self, '%s: no matches' % (token,))

def parse_atom(token, repo, return_none=False):
    """Use L{parserestrict.parse_match} to produce a single atom.

    This matches the restriction against the repo, raises
    AmbiguousQuery if they belong to multiple cat/pkgs, returns an
    atom otherwise.

    @param token: string to convert.
    @param repo: L{pkgcore.repository.prototype.tree} instance to search in.
    @param return_none: indicates if no matches raises or returns C{None}

    @return: an atom or C{None}.
    """
    # XXX this should be in parserestrict in some form, perhaps.
    restriction = parserestrict.parse_match(token)
    key_matches = set(x.key for x in repo.itermatch(restriction))
    if not key_matches:
        raise NoMatches(token)
    elif len(key_matches) > 1:
        raise AmbiguousQuery(token, sorted(key_matches))
    if isinstance(restriction, atom):
        # atom is guranteed to be fine, since it's cat/pkg
        return restriction
    return KeyedAndRestriction(restriction, key=key_matches.pop())


class Failure(ValueError):
    """Raised internally to indicate an "expected" failure condition."""


def unmerge(out, err, vdb, tokens, options, world_set=None):
    """Unmerge tokens. hackish, should be rolled back into the resolver"""
    all_matches = set()
    for token in tokens:
        # Catch restrictions matching across more than one category.
        # Multiple matches in the same category are acceptable.

        # The point is that matching across more than one category is
        # nearly always unintentional ("pmerge -C spork" without
        # realising there are sporks in more than one category), but
        # matching more than one cat/pkg is impossible without
        # explicit wildcards.
        restriction = parserestrict.parse_match(token)
        matches = vdb.match(restriction)
        if not matches:
            raise Failure('Nothing matches %s' % (token,))
        categories = set(pkg.category for pkg in matches)
        if len(categories) > 1:
            raise parserestrict.ParseError(
                '%s is in multiple categories (%s)' % (
                    token, ', '.join(set(pkg.key for pkg in matches))))
        all_matches.update(matches)

    matches = sorted(all_matches)
    out.write(out.bold, 'The following packages are to be unmerged:')
    out.prefix = [out.bold, ' * ', out.reset]
    for match in matches:
        out.write(match.cpvstr)
    out.prefix = []

    repo_obs = observer.file_repo_observer(ObserverFormatter(out))

    if options.pretend:
        return

    if (options.ask and not
        formatter.ask("Would you like to unmerge these packages?")):
        return
    return do_unmerge(options, out, err, vdb, matches, world_set, repo_obs)

def do_unmerge(options, out, err, vdb, matches, world_set, repo_obs):
    if vdb.frozen:
        if options.force:
            out.write(
                out.fg('red'), out.bold,
                'warning: vdb is frozen, overriding')
            vdb.frozen = False
        else:
            raise Failure('vdb is frozen')

    for idx, match in enumerate(matches):
        out.write("removing %i of %i: %s" % (idx + 1, len(matches), match))
        out.title("%i/%i: %s" % (idx + 1, len(matches), match))
        op = vdb.uninstall(match, observer=repo_obs)
        ret = op.finish()
        if not ret:
            if not options.ignore_failures:
                raise Failure('failed unmerging %s' % (match,))
            out.write(out.fg('red'), 'failed unmerging ', match)
        update_worldset(world_set, match, remove=True)
    out.write("finished; removed %i packages" % len(matches))


def get_pkgset(config, err, setname):
    try:
        return config.pkgset[setname]
    except KeyError:
        err.write('No set called %r!\nknown sets: %r' %
            (setname, config.pkgset.keys()))
        return None

def update_worldset(world_set, pkg, remove=False):
    if world_set is None:
        return
    if remove:
        try:
            world_set.remove(pkg)
        except KeyError:
            # nothing to remove, thus skip the flush
            return
    else:
        world_set.add(pkg)
    world_set.flush()

def main(options, out, err):
    config = options.config
    if options.debug:
        resolver.plan.limiters.add(None)

    domain = config.get_default('domain')
    vdb = domain.all_vdbs

    formatter = formatters[options.formatter](out=out, err=err,
        verbose=options.verbose, use_expand=domain.use_expand,
        use_expand_hidden=domain.use_expand_hidden)

    # This mode does not care about sets and packages so bypass all that.
    if options.unmerge:
        world_set = None
        if not options.oneshot:
            world_set = get_pkgset(config, err, "world")
            if world_set is None:
                err.write("Disable world updating via --oneshot, or fix your "
                    "configuration")
                return 1
        try:
            unmerge(
                out, err, vdb, options.targets, options, world_set)
        except (parserestrict.ParseError, Failure), e:
            out.error(str(e))
            return 1
        return

    all_repos = domain.all_repos
    repos = list(all_repos.trees)
    if options.usepkgonly or options.usepkg:
        if options.usepkgonly:
            repos = [
                repo for repo in all_repos.trees
                if getattr(repo, 'format_magic', None) != 'ebuild_src']
        else:
            repos = [
                repo for repo in all_repos.trees
                if getattr(repo, 'format_magic', None) == 'ebuild_built'] + [
                repo for repo in all_repos.trees
                if getattr(repo, 'format_magic', None) != 'ebuild_built']
        all_repos = multiplex.tree(*repos)

    atoms = []
    for setname in options.set:
        pkgset = get_pkgset(config, err, setname)
        if pkgset is None:
            return 1
        l = list(pkgset)
        if not l:
            out.write("skipping set %s: set is empty, nothing to update" % setname)
        else:
            atoms.extend(l)

    for token in options.targets:
        try:
            a = parse_atom(token, all_repos, return_none=True)
        except parserestrict.ParseError, e:
            out.error(str(e))
            return 1
        if a is None:
            if token in config.pkgset:
                out.error(
                    'No package matches %r, but there is a set with '
                    'that name. Use -s to specify a set.' % (token,))
                return 2
            elif not options.ignore_failures:
                out.error('No matches for %r; ignoring it' % token)
            else:
                return -1
        else:
            atoms.append(a)

    if not atoms:
        out.error('No targets specified; nothing to do')
        return 1

    atoms = lists.stable_unique(atoms)

    world_set = None
    if (not options.set or options.clean) and not options.oneshot:
        world_set = get_pkgset(config, err, 'world')
        if world_set is None:
            err.write("Disable world updating via --oneshot, or fix your "
                "configuration")
            return 1

    if options.upgrade:
        resolver_kls = resolver.upgrade_resolver
    else:
        resolver_kls = resolver.min_install_resolver

    extra_kwargs = {}
    if options.empty:
        extra_kwargs['resolver_cls'] = resolver.empty_tree_merge_plan

    resolver_inst = resolver_kls(
        vdb, repos, verify_vdb=options.deep, nodeps=options.nodeps,
        drop_cycles=options.ignore_cycles, force_replacement=options.replace,
        process_built_depends=options.with_built_depends,
        **extra_kwargs)

    if options.preload_vdb_state:
        out.write(out.bold, ' * ', out.reset, 'Preloading vdb... ')
        vdb_time = time()
        resolver_inst.load_vdb_state()
        vdb_time = time() - vdb_time
    else:
        vdb_time = 0.0

    failures = []
    resolve_time = time()
    out.write(out.bold, ' * ', out.reset, 'Resolving...')
    out.title('Resolving...')
    for restrict in atoms:
#        print "\ncalling resolve for %s..." % restrict
        ret = resolver_inst.add_atom(restrict)
        if ret:
            out.error('Resolver returned %r' % (ret,))
            out.error('resolution failed')
            failures.append(restrict)
            if not options.ignore_failures:
                break
    resolve_time = time() - resolve_time
    if failures:
        out.write()
        out.write('Failures encountered:')
        for restrict in failures:
            out.error("failed '%s'" % (restrict,))
            out.write('potentials:')
            match_count = 0
            for r in repo_utils.get_raw_repos(repos):
                l = r.match(restrict)
                if l:
                    out.write(
                        "repo %s: [ %s ]" % (r, ", ".join(str(x) for x in l)))
                    match_count += len(l)
            if not match_count:
                out.write("No matches found in %s" % (repos,))
            out.write()
            if not options.ignore_failures:
                return 1

    if options.clean:
        out.write(out.bold, ' * ', out.reset, 'Packages to be removed:')
        vset = set(vdb)
        len_vset = len(vset)
        vset.difference_update(y.pkg for y in
            resolver_inst.state.iter_ops(True))
        wipes = sorted(x for x in vset if x.package_is_real)
        for x in wipes:
            out.write("Remove %s" % x)
        out.write()
        if len(wipes):
            out.write("removing %i packages of %i installed, %0.2f%%." %
                (len(wipes), len_vset, 100*(len(wipes)/float(len_vset))))
        else:
            out.write("no packages to remove")
        if options.pretend:
            return 0
        if options.ask:
            if not formatter.ask("Do you wish to proceed?", default_answer=False):
                return 1
            out.write()
        repo_obs = observer.file_repo_observer(ObserverFormatter(out))
        do_unmerge(options, out, err, vdb, wipes, world_set, repo_obs)
        return 0

    changes = list(x for x in resolver_inst.state.iter_ops()
        if x.pkg.package_is_real)

    if options.ask or options.pretend:
        for op in changes:
            formatter.format(op)
        formatter.end()

    if options.verbose:
        out.write()
        out.title('Resolved')
        out.write(out.bold, '%.2f' % (resolve_time,), out.reset,
            ' seconds resolving')

    if vdb_time:
        out.write(out.bold, 'Took %.2f' % (vdb_time,), out.reset,
                  ' seconds to preload vdb state')
    if options.pretend:
        return

    if (options.ask and not
        formatter.ask("Would you like to merge these packages?")):
        return

    build_obs = observer.file_build_observer(ObserverFormatter(out))
    repo_obs = observer.file_repo_observer(ObserverFormatter(out))

    change_count = len(changes)
    for count, op in enumerate(changes):
        out.write("Processing %i of %i: %s" % (count + 1, change_count,
            op.pkg.cpvstr))
        out.title("%i/%i: %s" % (count + 1, change_count, op.pkg.cpvstr))
        if op.desc != "remove":
            if not options.fetchonly and options.debug:
                out.write("Forcing a clean of workdir")
            buildop = op.pkg.build(observer=build_obs, clean=True)
            if options.fetchonly:
                out.write("\n%i files required-" % len(op.pkg.fetchables))
                try:
                    ret = buildop.fetch()
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception, e:
                    ret = e
                if ret != True:
                    out.error("got %s for a phase execution for %s" % (ret, op.pkg))
                    if not options.ignore_failures:
                        return 1
                buildop.cleanup()
                del buildop, ret
                continue

            ret = None
            try:
                built_pkg = buildop.finalize()
                if built_pkg is False:
                    ret = built_pkg
            except format.errors, e:
                ret = e
            if ret is None:
                out.write()
                if op.desc == "replace":
                    if op.old_pkg == op.pkg:
                        out.write(">>> Reinstalling %s" % (built_pkg.cpvstr))
                    else:
                        out.write(">>> Replacing %s with %s" % (
                            op.old_pkg.cpvstr, built_pkg.cpvstr))
                    i = vdb.replace(op.old_pkg, built_pkg, observer=repo_obs)
                else:

                    out.write(">>> Installing %s" % built_pkg.cpvstr)
                    i = vdb.install(built_pkg, observer=repo_obs)
            else:
                out.error("Failed to build %s: %s" % (op.pkg, ret))
                if not options.ignore_failures:
                    return 1
                continue
            # force this explicitly- can hold onto a helluva lot more
            # then we would like.
            del built_pkg
        else:
            out.write(">>> Removing %s" % op.pkg.cpvstr)
            i = vdb.uninstall(op.pkg, observer=repo_objs)
        ret = i.finish()
        if ret != True:
            out.error("got %s for a phase execution for %s" % (ret, op.pkg))
            if not options.ignore_failures:
                return 1
        buildop.cleanup()
        if world_set:
            if op.desc == "remove":
                out.write('>>> Removing %s from world file' % op.pkg.cpvstr)
                update_worldset(world_set, op.pkg, remove=True)
            elif any(x.match(op.pkg) for x in atoms):
                out.write('>>> Adding %s to world file' % op.pkg.cpvstr)
                update_worldset(world_set, op.pkg)
    out.write("finished")
    return 0
