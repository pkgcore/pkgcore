# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

# more should be doc'd...
__all__ = ("OptionParser", "AmbiguousQuery", "NoMatches")

"""Mess with the resolver and vdb."""

from time import time

from pkgcore.util import commandline, parserestrict, repo_utils
from pkgcore.ebuild import resolver
from pkgcore.repository import multiplex
from pkgcore.operations import observer, format
from pkgcore.ebuild.atom import atom
from pkgcore.merge import errors as merge_errors
from pkgcore.restrictions import packages, values
from pkgcore.restrictions.boolean import AndRestriction, OrRestriction

from snakeoil import lists, currying
from snakeoil.compatibility import any, IGNORED_EXCEPTIONS
from pkgcore.resolver.util import reduce_to_failures

class OptionParser(commandline.OptionParser):

    enable_domain_options = True
    description = __doc__

    def _register_options(self):
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
        self.add_option('--verbose', '-v', action='store_true',
            help="be verbose in output")
        self.add_option('--ask', '-a', action='store_true',
            help="do the resolution, but ask to merge/fetch anything")
        self.add_option('--fetchonly', '-f', action='store_true',
            help="do only the fetch steps of the resolved plan")
        self.add_option('--newuse', '-N', action='store_true',
            help="check for changed useflags in installed packages "
                "(implies -1)")
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

    def _check_values(self, options, args):
        options.targets = [x for x in args if x[0] != '@']
        set_targets = [x[1:] for x in args if x[0] == '@']
        if any(not x for x in set_targets):
            self.error("empty set name specified via @")
        options.set.extend(set_targets)


        # TODO this is rather boilerplate-ish, the commandline module
        # should somehow do this for us.
        if options.formatter is None:
            options.formatter = options.config.get_default('pmerge_formatter')
            if options.formatter is None:
                self.error(
                    'No default formatter found, fix your configuration '
                    'or pass --formatter (Valid formatters: %s)' % (
                        ', '.join(options.config.pmerge_formatter),))

        # this may seem odd, but via touching this attribute we ensure that
        # there is a valid domain- specifically it'll throw a config exception
        # if that's not the case.
        options.domain

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
        if options.newuse:
            options.oneshot = True
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
    """Use :obj:`parserestrict.parse_match` to produce a single atom.

    This matches the restriction against the repo, raises
    AmbiguousQuery if they belong to multiple cat/pkgs, returns an
    atom otherwise.

    :param token: string to convert.
    :param repo: :obj:`pkgcore.repository.prototype.tree` instance to search in.
    :param return_none: indicates if no matches raises or returns C{None}

    :return: an atom or C{None}.
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
    return packages.KeyedAndRestriction(restriction, key=key_matches.pop())


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

    repo_obs = observer.repo_observer(observer.formatter_output(out),
        not options.debug)

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
        op = options.domain.uninstall_pkg(match, observer=repo_obs)
        ret = op.finish()
        if not ret:
            if not options.ignore_failures:
                raise Failure('failed unmerging %s' % (match,))
            out.write(out.fg('red'), 'failed unmerging ', match)
        update_worldset(world_set, match, remove=True)
    out.write("finished; removed %i packages" % len(matches))


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
                    ','.join(str(x) for x in step[1]))
            elif step[0] == 'blocker':
                out.write("blocker %s failed due to %s existing" % (step[1],
                    ', '.join(str(x) for x in step[2])))
            elif step[0] == 'cycle':
                out.write("%s cycle on %s: %s" % (step[1].mode, step[1].atom, step[2]))
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
        for x in xrange(3):
            out.first_prefix.pop()

def slotatom_if_slotted(repos, checkatom):
    """check repos for more than one slot of given atom"""

    if checkatom.slot is None or checkatom.slot[0] != "0":
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
    world_set = world_list = options.get_pkgset(err, "world")
    if options.oneshot:
        world_set = None

    formatter = options.formatter(out=out, err=err,
        use_expand=domain.use_expand,
        use_expand_hidden=domain.use_expand_hidden,
        disabled_use=domain.disabled_use,
        world_list=world_list, verbose=options.verbose)

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


    source_repos = domain.source_repositories
    installed_repos = domain.installed_repositories

    if options.usepkgonly:
        source_repos = source_repos.change_repos(x for x in source_repos
            if getattr(x, 'format_magic', None) != 'ebuild_src')
    elif options.usepkg:
        repo_types = [(getattr(x, 'format_magic', None) == 'ebuild_built', x)
            for x in source_repos]
        source_repos = source_repos.change_repos(
            [x[1] for x in repo_types if x[0]] +
            [x[1] for x in repo_types if not x[0]]
        )

    atoms = []
    for setname in options.set:
        pkgset = options.get_pkgset(err, setname)
        if pkgset is None:
            return 1
        l = list(pkgset)
        if not l:
            out.write("skipping set %s: set is empty, nothing to update" % setname)
        else:
            atoms.extend(l)

    for token in options.targets:
        try:
            a = parse_atom(token, source_repos.combined, return_none=True)
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

    # XXX: This should recurse on deep
    if options.newuse:
        out.write(out.bold, ' * ', out.reset, 'Scanning for changed USE...')
        out.title('Scanning for changed USE...')
        restrict = packages.PackageRestriction('category',
            values.StrExactMatch('virtual'), negate=True)
        if atoms:
            restrict = AndRestriction(restrict, OrRestriction(*atoms))
        for inst_pkg in installed_repos.itermatch(restrict):
            src_pkgs = source_repos.match(inst_pkg.versioned_atom)
            if src_pkgs:
                src_pkg = max(src_pkgs)
                inst_use = set(use.lstrip("+-") for use in inst_pkg.iuse)
                src_use = set(use.lstrip("+-") for use in src_pkg.iuse)
                oldflags = inst_use & inst_pkg.use
                newflags = src_use & src_pkg.use
                changed_flags = (oldflags ^ newflags) | (inst_pkg.iuse ^ src_pkg.iuse)
                if changed_flags:
                    atoms.append(src_pkg.versioned_atom)

#    left intentionally in place for ease of debugging.
#    from guppy import hpy
#    hp = hpy()
#    hp.setrelheap()

    resolver_inst = resolver_kls(
        installed_repos.repositories, source_repos.repositories,
        verify_vdb=options.deep, nodeps=options.nodeps, drop_cycles=options.ignore_cycles,
        force_replacement=options.replace, process_built_depends=options.with_built_depends,
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
    out.title('Resolving...')
    out.write(out.bold, ' * ', out.reset, 'Resolving...')
    orig_atoms = atoms[:]
    ret = resolver_inst.add_atoms(atoms, finalize=True)
    while ret:
        out.error('resolution failed')
        restrict = ret[0][0]
        just_failures = reduce_to_failures(ret[1])
        display_failures(out, just_failures, debug=options.debug)
        failures.append(restrict)
        if not options.ignore_failures:
            break
        out.write("restarting resolution")
        atoms = [x for x in atoms if x != restrict]
        resolver_inst.reset()
        ret = resolver_inst.add_atoms(atoms, finalize=True)
    resolve_time = time() - resolve_time

    if failures:
        out.write()
        out.write('Failures encountered:')
        for restrict in failures:
            out.error("failed '%s'" % (restrict,))
            out.write('potentials:')
            match_count = 0
            for r in repo_utils.get_raw_repos(source_repos.repositories):
                l = r.match(restrict)
                if l:
                    out.write(
                        "repo %s: [ %s ]" % (r, ", ".join(str(x) for x in l)))
                    match_count += len(l)
            if not match_count:
                out.write("No matches found in %s" % (source_repos.repositories,))
            out.write()
            if not options.ignore_failures:
                return 1

    resolver_inst.free_caches()

    if options.clean:
        out.write(out.bold, ' * ', out.reset, 'Packages to be removed:')
        vset = set(installed_repos.combined)
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
        repo_obs = observer.repo_observer(observer.formatter_output(out),
            not options.debug)
        do_unmerge(options, out, err, installed_repos.combined, wipes, world_set, repo_obs)
        return 0

    if options.debug:
        out.write()
        out.write(out.bold, ' * ', out.reset, 'debug: all ops')
        out.first_prefix.append(" ")
        plan_len = len(str(len(resolver_inst.state.plan)))
        for pos, op in enumerate(resolver_inst.state.plan):
            out.write(str(pos + 1).rjust(plan_len), ': ', str(op))
        out.first_prefix.pop()
        out.write(out.bold, ' * ', out.reset, 'debug: end all ops')
        out.write()

    changes = resolver_inst.state.ops(only_real=True)

    build_obs = observer.build_observer(observer.formatter_output(out),
        not options.debug)
    repo_obs = observer.repo_observer(observer.formatter_output(out),
        not options.debug)

    if options.debug:
        out.write(out.bold, " * ", out.reset, "running sanity checks")
    if not changes.run_sanity_checks(domain):
        out.error("sanity checks failed.  please resolve them and try again.")
        return 1
    if options.debug:
        out.write(out.bold, " * ", out.reset, "finished sanity checks")

    if options.ask or options.pretend:
        for op in changes:
            formatter.format(op)
        formatter.end()


    if vdb_time:
        out.write(out.bold, 'Took %.2f' % (vdb_time,), out.reset,
                  ' seconds to preload vdb state')
    if not changes:
        out.write("Nothing to merge.")
        return

    if options.pretend:
        if options.verbose:
            out.write(out.bold, ' * ', out.reset, "resolver plan required %i ops\n" % (len(resolver_inst.state.plan),))
        return

    if (options.ask and not
        formatter.ask("Would you like to merge these packages?")):
        return

    change_count = len(changes)

    # left in place for ease of debugging.
    cleanup = []
    try:
        for count, op in enumerate(changes):
            for func in cleanup:
                func()

            cleanup = []

            out.write("Processing %i of %i: %s" % (count + 1, change_count,
                op.pkg.cpvstr))
            out.title("%i/%i: %s" % (count + 1, change_count, op.pkg.cpvstr))
            if op.desc != "remove":
                cleanup = [op.pkg.release_cached_data]

                if not options.fetchonly and options.debug:
                    out.write("Forcing a clean of workdir")

                pkg_ops = domain.pkg_operations(op.pkg, observer=build_obs)
                out.write("\n%i files required-" % len(op.pkg.fetchables))
                try:
                    ret = pkg_ops.run_if_supported("fetch", or_return=True)
                except IGNORED_EXCEPTIONS:
                    raise
                except Exception, e:
                    ret = e
                if ret is not True:
                    out.write("\n")
                    out.error("fetching failed for %s" % (op.pkg,))
                    if not options.ignore_failures:
                        return 1
                    continue
                if options.fetchonly:
                    continue

                buildop = pkg_ops.run_if_supported("build", or_return=None)
                pkg = op.pkg
                if buildop is not None:
                    out.write("building %s" % (op.pkg,))
                    result = False
                    try:
                        result = buildop.finalize()
                    except format.errors, e:
                        out.error("caught exception building %s: % s" % (op.pkg, e))
                    else:
                        if result is False:
                            out.error("failed building %s" % (op.pkg,))
                    if result is False:
                        if not options.ignore_failures:
                            return 1
                        continue
                    pkg = result
                    cleanup.append(pkg.release_cached_data)
                    pkg_ops = domain.pkg_operations(pkg, observer=build_obs)
                    cleanup.append(buildop.cleanup)

                cleanup.append(currying.partial(pkg_ops.run_if_supported, "cleanup"))
                pkg = pkg_ops.run_if_supported("localize", or_return=pkg)
                # wipe this to ensure we don't inadvertantly use it further down;
                # we aren't resetting it after localizing, so could have the wrong
                # set of ops.
                del pkg_ops

                out.write()
                if op.desc == "replace":
                    if op.old_pkg == pkg:
                        out.write(">>> Reinstalling %s" % (pkg.cpvstr))
                    else:
                        out.write(">>> Replacing %s with %s" % (
                            op.old_pkg.cpvstr, pkg.cpvstr))
                    i = domain.replace_pkg(op.old_pkg, pkg, repo_obs)
                    cleanup.append(op.old_pkg.release_cached_data)
                else:
                    out.write(">>> Installing %s" % (pkg.cpvstr,))
                    i = domain.install_pkg(pkg, repo_obs)

                # force this explicitly- can hold onto a helluva lot more
                # then we would like.
            else:
                out.write(">>> Removing %s" % op.pkg.cpvstr)
                i = domain.uninstall_pkg(op.pkg, repo_obs)
            try:
                ret = i.finish()
            except merge_errors.BlockModification, e:
                out.error("Failed to merge %s: %s" % (op.pkg, e))
                if not options.ignore_failures:
                    return 1
                continue

            # while this does get handled through each loop, wipe it now; we don't need
            # that data, thus we punt it now to keep memory down.
            # for safety sake, we let the next pass trigger a release also-
            # mainly to protect against any code following triggering reloads
            # basically, be protective

            if world_set is not None:
                if op.desc == "remove":
                    out.write('>>> Removing %s from world file' % op.pkg.cpvstr)
                    removal_pkg = slotatom_if_slotted(source_repos.combined, op.pkg.versioned_atom)
                    update_worldset(world_set, removal_pkg, remove=True)
                elif not options.oneshot and any(x.match(op.pkg) for x in atoms):
                    if not options.upgrade:
                        out.write('>>> Adding %s to world file' % op.pkg.cpvstr)
                        add_pkg = slotatom_if_slotted(source_repos.combined, op.pkg.versioned_atom)
                        update_worldset(world_set, add_pkg)


#    again... left in place for ease of debugging.
#    except KeyboardInterrupt:
#        import pdb;pdb.set_trace()
#    else:
#        import pdb;pdb.set_trace()
    finally:
        pass

    # the final run from the loop above doesn't invoke cleanups;
    # we could ignore it, but better to run it to ensure nothing is inadvertantly
    # held on the way out of this function.
    # makes heappy analysis easier if we're careful about it.
    for func in cleanup:
        func()

    # and wipe the reference to the functions to allow things to fall out of
    # memory.
    cleanup = []

    out.write("finished")
    return 0
