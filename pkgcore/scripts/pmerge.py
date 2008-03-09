# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Mess with the resolver and vdb."""

from time import time

from pkgcore.util import commandline, parserestrict, repo_utils
from pkgcore.ebuild import resolver
from pkgcore.repository import multiplex
from pkgcore.interfaces import observer, format
from pkgcore.pkgsets.glsa import KeyedAndRestriction
from pkgcore.ebuild.atom import atom
from pkgcore.merge import errors as merge_errors
from pkgcore.restrictions import packages, values

from snakeoil import lists
from snakeoil.formatters import ObserverFormatter
from snakeoil.compatibility import any
from pkgcore.resolver.util import reduce_to_failures

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
            help='try to upgrade already installed packages/dependencies')
        self.add_option('--set', '-s', action='append',
            help='specify a pkgset to use')
        self.add_option('--ignore-failures', action='store_true',
            help='ignore resolution failures')
        self.add_option('--preload-vdb-state', action='store_true',
            help=\
"""enable preloading of the installed packages database
This causes the resolver to work with a complete graph, thus disallowing
actions that conflict with installed packages.  If disabled, it's possible
for the requested action to conflict with already installed dependencies
that aren't involved in the graph of the requested operation""")

        self.add_option('--pretend', '-p', action='store_true',
            help="do the resolution, but don't merge/fetch anything")
        self.add_option('--ask', '-a', action='store_true',
            help="do the resolution, but ask to merge/fetch anything")
        self.add_option('--fetchonly', '-f', action='store_true',
            help="do only the fetch steps of the resolved plan")
        self.add_option('--newuse', '-N', action='store_true', 
            help="check for changed useflags in installed packages")
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
            '--formatter', '-F', action='callback', type='string',
            callback=commandline.config_callback,
            callback_args=('pmerge_formatter',),
            help='which formatter to output --pretend or --ask output through.')
        self.add_option('--domain', action='callback', type='string',
            callback=commandline.config_callback, callback_args=('domain',),
            help='specify which domain to use; else uses the "default" domain')

    def check_values(self, options, args):
        options, args = commandline.OptionParser.check_values(
            self, options, args)
        options.targets = args

        # TODO this is rather boilerplate-ish, the commandline module
        # should somehow do this for us.
        if options.formatter is None:
            options.formatter = options.config.get_default('pmerge_formatter')
            if options.formatter is None:
                self.error(
                    'No default formatter found, fix your configuration '
                    'or pass --formatter (Valid formatters: %s)' % (
                        ', '.join(options.config.pmerge_formatter),))

        if options.domain is None:
            options.domain = options.config.get_default('domain')
            if options.domain is None:
                self.error(
                    'No default domain found, fix your configuration or pass '
                    '--domain (valid domains: %s)' %
                    (', '.join(options.config.domain),))

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
        if not options.targets and not options.set and not options.newuse:
            self.error('Need at least one atom/set')
        if options.newuse and options.set:
            self.error("Don't specify --newuse when using sets, use it standalone")
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
    restriction = parserestrict.parse_match(str(token))
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


def unmerge(out, err, vdb, tokens, options, formatter, world_set=None):
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

def display_failures(out, sequence, first_level=True, debug=False):
    """when resolution fails, display a nicely formatted message"""

    sequence = iter(sequence)
    frame = sequence.next()
    if first_level:
        # pops below need to exactly match.
        out.first_prefix.extend((out.fg("red"), "!!!", out.reset))
    out.first_prefix.append(" ")
    out.write("request %s, mode %s" % (frame.atom, frame.mode))
    for pkg, steps in sequence:
        out.write("trying %s" % str(pkg.cpvstr))
        out.first_prefix.append(" ")
        for step in steps:
            if isinstance(step, list):
                display_failures(out, step, False, debug=debug)
            elif step[0] == 'reduce':
                out.write("removing choices involving %s" %
                    ','.join(map(str,step[1])))
            elif step[0] == 'blocker':
                out.write("blocker %s failed due to %s existing" % (step[1],
                    ', '.join(str(x) for x in step[2])))
            elif step[0] == 'cycle':
                out.write("%s cycle on %s: %s" % (step[2].mode, step[2].atom, step[3]))
            elif step[0] == 'viable' and not step[1]:
                out.write("%s: failed %s" % (step[3], step[4]))
            elif step[0] == 'choice':
                if not step[2]:
                    out.write("failed due to %s" % (step[3],))
            elif step[0] == "debug":
                if debug:
                    out.write(step[1])
            else:
                out.write(step)
        out.first_prefix.pop()
    out.first_prefix.pop()
    if first_level:
        [out.first_prefix.pop() for x in (1,2,3)]

def slotatom_if_slotted(repos, checkatom):
    """check repos for more than one slot of given atom"""

    if checkatom.slot is None or ncheckatom.slot[0] != "0":
        return checkatom

    found_slots = ()
    pkgs = repos.itermatch(checkatom, sorter=sorted)
    for pkg in pkgs:
        found_slots.update(pkg.slot[0])

    if len(found_slots) == 1:
        return atom(checkatom.key)

    return checkatom

def update_worldset(world_set, pkg, remove=False):
    """record/kill given atom in worldset"""

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

    domain = options.domain
    livefs_repos = domain.all_livefs_repos
    world_set = world_list = get_pkgset(config, err, "world")
    if options.oneshot:
        world_set = None

    formatter = options.formatter(out=out, err=err,
        use_expand=domain.use_expand,
        use_expand_hidden=domain.use_expand_hidden,
        disabled_use=domain.disabled_use,
        world_list=world_list)

    # This mode does not care about sets and packages so bypass all that.
    if options.unmerge:
        if not options.oneshot:
            if world_set is None:
                err.write("Disable world updating via --oneshot, or fix your "
                    "configuration")
                return 1
        try:
            unmerge(
                out, err, livefs_repos, options.targets, options, formatter, world_set)
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

    if not atoms and not options.newuse:
        out.error('No targets specified; nothing to do')
        return 1

    atoms = lists.stable_unique(atoms)

    if (not options.set or options.clean) and not options.oneshot:
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
    if options.debug:
        extra_kwargs['debug'] = True

    if options.newuse:
        out.write(out.bold, ' * ', out.reset, 'Scanning for changed USE...')
        out.title('Scanning for changed USE...')
        for inst_pkg in livefs_repos.itermatch(packages.PackageRestriction('category',
            values.StrExactMatch('virtual'), negate=True)):
            src_pkgs = all_repos.match(inst_pkg.versioned_atom)
            if src_pkgs:
                src_pkg = max(src_pkgs)
                inst_use = set(use.lstrip("+-") for use in inst_pkg.iuse)
                src_use = set(use.lstrip("+-") for use in src_pkg.iuse)
                oldflags = inst_use & inst_pkg.use
                newflags = src_use & src_pkg.use
                changed_flags = (oldflags ^ newflags) | (inst_pkg.iuse ^ src_pkg.iuse)
                if changed_flags:
                    #import pdb;pdb.set_trace()
                    atoms.append(src_pkg.versioned_atom)

    resolver_inst = resolver_kls(
        livefs_repos, repos, verify_vdb=options.deep, nodeps=options.nodeps,
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
        ret = resolver_inst.add_atom(restrict)
        if ret:
            out.error('resolution failed')
            just_failures = reduce_to_failures(ret[1])
            display_failures(out, just_failures, debug=options.debug)
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
        vset = set(livefs_repos)
        len_vset = len(vset)
        vset.difference_update(y.pkg for y in
            resolver_inst.state.iter_ops(True))
        wipes = sorted(x for x in vset if x.package_is_real)
        for x in wipes:
            out.write("Remove %s" % x)
        out.write()
        if wipes:
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
        do_unmerge(options, out, err, livefs_repos, wipes, world_set, repo_obs)
        return 0

    changes = list(x for x in resolver_inst.state.iter_ops()
        if x.pkg.package_is_real)

    if options.ask or options.pretend:
        for op in changes:
            formatter.format(op)
        formatter.end()


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
            if ret is not None:
                out.error("Failed to build %s: %s" % (op.pkg, ret))
                if not options.ignore_failures:
                    return 1
                continue

            out.write()
            if op.desc == "replace":
                if op.old_pkg == op.pkg:
                    out.write(">>> Reinstalling %s" % (built_pkg.cpvstr))
                else:
                    out.write(">>> Replacing %s with %s" % (
                        op.old_pkg.cpvstr, built_pkg.cpvstr))
                i = livefs_repos.replace(op.old_pkg, built_pkg, observer=repo_obs)

            else:
                out.write(">>> Installing %s" % built_pkg.cpvstr)
                i = livefs_repos.install(built_pkg, observer=repo_obs)

            # force this explicitly- can hold onto a helluva lot more
            # then we would like.
            del built_pkg
        else:
            out.write(">>> Removing %s" % op.pkg.cpvstr)
            i = livefs_repos.uninstall(op.pkg, observer=repo_obs)
        try:
            ret = i.finish()
        except merge_errors.BlockModification, e:
            out.error("Failed to merge %s: %s" % (op.pkg, e))
            if not options.ignore_failures:
                return 1
            continue

        buildop.cleanup()
        if world_set:
            if op.desc == "remove":
                out.write('>>> Removing %s from world file' % op.pkg.cpvstr)
                removal_pkg = slotatom_if_slotted(all_repos, op.pkg.versioned_atom)
                update_worldset(world_set, removal_pkg, remove=True)
            elif not options.oneshot and any(x.match(op.pkg) for x in atoms):
                if not options.upgrade:
                    out.write('>>> Adding %s to world file' % op.pkg.cpvstr)
                    add_pkg = slotatom_if_slotted(all_repos, op.pkg.versioned_atom)
                    update_worldset(world_set, add_pkg)
    out.write("finished")
    return 0
