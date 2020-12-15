"""package merging and unmerging interface

pmerge is the main command-line utility for merging and unmerging packages on a
system. It provides an interface to install, update, and uninstall ebuilds from
source or binary packages.
"""

# more should be doc'd...
__all__ = ("AmbiguousQuery", "NoMatches")

import sys
from functools import partial
from textwrap import dedent
from time import time

from snakeoil.cli.exceptions import ExitException
from snakeoil.sequences import iflatten_instance, stable_unique
from snakeoil.strings import pluralism

from ..ebuild import resolver, restricts
from ..ebuild.atom import atom
from ..ebuild.misc import run_sanity_checks
from ..merge import errors as merge_errors
from ..operations import format, observer
from ..repository.util import get_raw_repos
from ..repository.virtual import RestrictionRepo
from ..resolver.util import reduce_to_failures
from ..restrictions import packages
from ..restrictions.boolean import OrRestriction
from ..util import commandline, parserestrict

argparser = commandline.ArgumentParser(
    domain=True, description=__doc__, script=(__file__, __name__))
argparser.add_argument(
    nargs='*', dest='targets', metavar='TARGET',
    action=commandline.StoreTarget, use_sets='sets',
    help="extended package matching",
    docs=commandline.StoreTarget.__doc__.split('\n')[1:])

operation_args = argparser.add_argument_group('operations')
operation_options = operation_args.add_mutually_exclusive_group()
operation_options.add_argument(
    '-u', '--upgrade', action='store_true',
    help='try to upgrade installed pkgs/deps',
    docs="""
        Try to upgrade specified targets to the latest visible version. Note
        that altered package visibility due to keywording or masking can often
        hide the latest versions of packages, especially for stable
        configurations.
    """)
operation_options.add_argument(
    '-d', '--downgrade', action='store_true',
    help='try to downgrade installed pkgs/deps',
    docs="""
        Try to downgrade specified targets to a lower visible version
        compared to what's currently installed.

        Useful for reverting to the previously installed package version;
        however, note that the -O/--nodeps option is generally used with this
        otherwise lots of downgrades will be pulled into the resolved deptree.
    """)
operation_options.add_argument(
    '-C', '--unmerge', action='store_true',
    help='unmerge packages',
    docs="""
        Target packages for unmerging from the system.

        WARNING: This does not ask for user confirmation for any targets so
        it's possible to quickly break a system.
    """)
operation_options.add_argument(
    '--clean', action='store_true',
    help='remove installed packages not referenced by any target pkgs/sets',
    docs="""
        Remove installed packages that aren't referenced by any target packages
        or sets. This defaults to using the world and system sets if no targets
        are specified.

        Use with *caution*, this option used incorrectly can render your system
        unusable. Note that this implies --deep.
    """)
operation_options.add_argument(
    '--list-sets', action='store_true',
    help='display the list of available package sets')

resolution_options = argparser.add_argument_group("resolver options")
resolution_options.add_argument(
    '-p', '--pretend', action='store_true',
    help="only perform the dep resolution",
    docs="""
        Resolve package dependencies and display the results without performing
        any merges.
    """)
resolution_options.add_argument(
    '-a', '--ask', action='store_true',
    help="ask for user confirmation after dep resolution",
    docs="""
        Perform the dependency resolution, but ask for user confirmation before
        beginning the fetch/build/merge process. The choice defaults to yes so
        pressing the "Enter" key will trigger acceptance.
    """)
resolution_options.add_argument(
    '-f', '--fetchonly', action='store_true',
    help="do only the fetch steps of the resolved plan",
    docs="""
        Only perform fetching of all targets from SRC_URI based on the current
        USE configuration.
    """)
resolution_options.add_argument(
    '-1', '--oneshot', action='store_true',
    help="do not record changes in the world file",
    docs="""
        Build and merge packages normally, but do not add any targets to the
        world file. Note that this is forcibly enabled if a package set is
        specified.
    """)
resolution_options.add_argument(
    '-D', '--deep', action='store_true',
    help='force the resolver to verify installed deps',
    docs="""
        Force dependency resolution across the entire dependency tree for all
        specified targets.
    """)
resolution_options.add_argument(
    '-N', '--newuse', action='store_true',
    help="add installed pkgs with changed useflags to targets",
    docs="""
        Include installed packages with USE flag changes in the list of viable
        targets for rebuilding.

        USE flag changes include flags being added, removed, enabled, or
        disabled with regards to a package. USE flag changes can occur via
        ebuild alterations, profile updates, or local configuration
        modifications.

        Note that this option implies -1/--oneshot.
    """)
resolution_options.add_argument(
    '-i', '--ignore-cycles', action='store_true',
    help="ignore unbreakable dep cycles",
    docs="""
        Ignore dependency cycles if they're found to be unbreakable; for
        example: a depends on b, and b depends on a, with neither built.
    """)
resolution_options.add_argument(
    '--with-bdeps', action='store_true',
    help="process build deps for built packages",
    docs="""
        Pull in build time dependencies for built packages during dependency
        resolution, by default they're ignored.
    """)
resolution_options.add_argument(
    '-O', '--nodeps', action='store_true',
    help='disable dependency resolution',
    docs="""
        Build and merge packages without resolving any dependencies.
    """)
resolution_options.add_argument(
    '-o', '--onlydeps', action='store_true',
    help='only merge the deps of the specified packages',
    docs="""
        Build and merge only the dependencies for the packages specified.
    """)
resolution_options.add_argument(
    '-n', '--noreplace', action='store_false', dest='replace',
    help="don't reinstall target pkgs that are already installed",
    docs="""
        Skip packages that are already installed. By default when running
        without this option, any specified target packages will be remerged
        regardless of if they are already installed.
    """)
resolution_options.add_argument(
    '-b', '--buildpkg', action='store_true',
    help="build binpkgs",
    docs="""
        Force binary packages to be built for all merged packages.
    """)
resolution_options.add_argument(
    '-k', '--usepkg', action='store_true',
    help="prefer to use binpkgs",
    docs="""
        Binary packages are preferred over ebuilds when performing dependency
        resolution.
    """)
resolution_options.add_argument(
    '-K', '--usepkgonly', action='store_true',
    help="use only binpkgs",
    docs="""
        Only binary packages are considered when performing dependency
        resolution.
    """)
resolution_options.add_argument(
    '-S', '--source-only', action='store_true',
    help="use only ebuilds, no binpkgs",
    docs="""
        Only ebuilds are considered when performing dependency
        resolution.
    """)
resolution_options.add_argument(
    '-e', '--empty', action='store_true',
    help="force rebuilding of all involved packages",
    docs="""
        Force all targets and their dependencies to be rebuilt.
    """)
resolution_options.add_argument(
    '-x', '--exclude', dest='excludes', metavar='TARGET[,TARGET,...]',
    action=commandline.StoreTarget, separator=',',
    help='inject packages into the installed set',
    docs="""
        Comma-separated list of targets to pretend are installed.

        This supports extended package globbing, e.g. ``'dev-python/*'``
        equates to faking the entire dev-python category is installed.
    """)
resolution_options.add_argument(
    '--ignore-failures', action='store_true',
    help='ignore failures while running all types of tasks',
    docs="""
        Skip failures during the following phases: sanity checks
        (pkg_pretend), fetching, dep resolution, and (un)merging.
    """)
resolution_options.add_argument(
    '--force', action='store_true',
    dest='force',
    help="force changes to a repo, regardless of if it's frozen",
    docs="""
        Force (un)merging on the livefs (vdb), regardless of if it's frozen.
    """)
resolution_options.add_argument(
    '--preload-vdb-state', action='store_true',
    help="enable preloading of the installed packages database",
    docs="""
        Preload the installed package database which causes the resolver to
        work with a complete graph, thus disallowing actions that conflict with
        installed packages. If disabled, it's possible for the requested action
        to conflict with already installed dependencies that aren't involved in
        the graph of the requested operation.
    """)

output_options = argparser.add_argument_group("output options")
output_options.add_argument(
    '--quiet-repo-display', action='store_true',
    help="use indexes instead of ::repo suffixes in dep resolution output",
    docs="""
        In the package merge list display, suppress ::repo output and instead
        use index numbers to indicate which repos packages come from.
    """)
output_options.add_argument(
    '-F', '--formatter', priority=90, metavar='FORMATTER',
    action=commandline.StoreConfigObject, get_default=True,
    config_type='pmerge_formatter',
    help='output formatter to use',
    docs="""
        Select an output formatter to use for text formatting of --pretend or
        --ask output, currently available formatters include the following:
        basic, pkgcore, portage, portage-verbose, and paludis.

        The basic formatter is the nearest to simple text output and is
        intended for scripting while the portage/portage-verbose formatter
        closely emulates portage output and is used by default.
    """)


class AmbiguousQuery(parserestrict.ParseError):
    """Exception for multiple matches where a single match is required."""
    def __init__(self, token, keys):
        self.token = token
        self.keys = keys

    def __str__(self):
        return f"multiple matches for {self.token!r}: {', '.join(map(str, self.keys))}"


class NoMatches(parserestrict.ParseError):
    """Exception for no matches where at least one match is required."""
    def __init__(self, token):
        super().__init__(f'{token!r}: no matches')


class Failure(ValueError):
    """Raised internally to indicate an "expected" failure condition."""


def unmerge(out, err, installed_repos, targets, options, formatter, world_set=None):
    """Unmerge tokens. hackish, should be rolled back into the resolver"""
    # split real and virtual repos
    vdb = installed_repos.real.combined
    fake_vdb = installed_repos.virtual.combined

    matches = set()
    fake = set()
    unknown = set()
    for token, restriction in targets:
        # Catch restrictions matching across more than one category.
        # Multiple matches in the same category are acceptable.

        # The point is that matching across more than one category is
        # nearly always unintentional ("pmerge -C spork" without
        # realising there are sporks in more than one category), but
        # matching more than one cat/pkg is impossible without
        # explicit wildcards.
        installed = vdb.match(restriction)
        if not installed:
            fake_pkgs = fake_vdb.match(restriction)
            if fake_pkgs:
                fake.update(fake_pkgs)
            else:
                unknown.add(token)
            continue
        categories = set(pkg.category for pkg in installed)
        if len(categories) > 1:
            raise parserestrict.ParseError(
                "%r is in multiple categories (%s)" % (
                    token, ', '.join(sorted(set(pkg.key for pkg in installed)))))
        matches.update(installed)

    # fail out if no matches are found, otherwise just output a notification
    if unknown:
        unknowns = ', '.join(map(repr, unknown))
        if matches:
            err.write(f"Skipping unknown matches: {unknowns}\n")
        else:
            raise Failure(f"no matches found: {unknowns}")

    if fake:
        err.write('Skipping virtual pkg%s: %s' % (
            pluralism(fake_pkgs),
            ', '.join(f'{x.versioned_atom}::{x.repo_id}' for x in fake)))

    if matches:
        out.write(out.bold, 'The following packages are to be unmerged:')
        out.prefix = [out.bold, ' * ', out.reset]
        for pkg in matches:
            out.write(pkg.cpvstr)
        out.prefix = []

        repo_obs = observer.repo_observer(
            observer.formatter_output(out), debug=options.debug)

        if options.pretend:
            return

        if (options.ask and not formatter.ask("Would you like to unmerge these packages?")):
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
        out.write(f"removing {idx + 1} of {len(matches)}: {match}")
        out.title(f"{idx + 1}/{len(matches)}: {match}")
        op = options.domain.uninstall_pkg(match, observer=repo_obs)
        ret = op.finish()
        if not ret:
            if not options.ignore_failures:
                raise Failure(f'failed unmerging {match}')
            out.write(out.fg('red'), 'failed unmerging ', match)
        pkg = slotatom_if_slotted(vdb, match.versioned_atom)
        update_worldset(world_set, pkg, remove=True)
    out.write(f"finished; removed {len(matches)} packages")


def display_failures(out, sequence, first_level=True, debug=False):
    """when resolution fails, display a nicely formatted message"""

    sequence = iter(sequence)
    frame = next(sequence)
    if first_level:
        # pops below need to exactly match.
        out.first_prefix.extend((out.fg("red"), "!!!", out.reset))
    out.first_prefix.append(" ")
    out.write(f"request {frame.atom}, mode {frame.mode}")
    for pkg, steps in sequence:
        out.write(f"trying {pkg.cpvstr}")
        out.first_prefix.append(" ")
        for step in steps:
            if isinstance(step, list):
                display_failures(out, step, False, debug=debug)
            elif step[0] == 'reduce':
                out.write("removing choices involving %s" %
                          ', '.join(str(x) for x in step[1]))
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
        for x in range(3):
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


@argparser.bind_final_check
def _validate(parser, namespace):
    # nothing to validate if listing pkgsets
    if namespace.list_sets:
        return

    if namespace.unmerge:
        if namespace.sets:
            parser.error("using sets with -C probably isn't wise, aborting")
        if not namespace.targets:
            parser.error("you must provide at least one atom")

    if namespace.clean:
        if namespace.sets or namespace.targets:
            parser.error(
                "--clean currently cannot be used w/ any sets or targets given")
        namespace.sets = ('world', 'system')
        namespace.deep = True
        namespace.replace = False
        if namespace.usepkgonly or namespace.usepkg or namespace.source_only:
            parser.error(
                '--clean cannot be used with any of the following options: '
                '--usepkg --usepkgonly --source-only')
    elif namespace.usepkgonly and namespace.usepkg:
        parser.error('--usepkg is redundant when --usepkgonly is used')
    elif (namespace.usepkgonly or namespace.usepkg) and namespace.source_only:
        parser.error("--source-only cannot be used with --usepkg nor --usepkgonly")
    elif namespace.nodeps and namespace.onlydeps:
        parser.error("-O/--nodeps cannot be used with -o/--onlydeps (it's a no-op)")

    if namespace.sets:
        unknown_sets = set(namespace.sets).difference(namespace.config.pkgset)
        if unknown_sets:
            parser.error("unknown set%s: %s (available sets: %s)" % (
                pluralism(unknown_sets),
                ', '.join(sorted(map(repr, unknown_sets))),
                ', '.join(sorted(namespace.config.pkgset))))
        namespace.sets = [(x, namespace.config.pkgset[x]) for x in namespace.sets]
    if namespace.upgrade or namespace.downgrade:
        namespace.replace = False
    if not namespace.targets and not namespace.sets:
        parser.error('please specify at least one atom or nonempty set')
    if namespace.newuse:
        namespace.oneshot = True

    if namespace.upgrade:
        namespace.resolver_kls = resolver.upgrade_resolver
    elif namespace.downgrade:
        namespace.resolver_kls = resolver.downgrade_resolver
    else:
        namespace.resolver_kls = resolver.min_install_resolver


def parse_target(restriction, repo, installed_repos, return_none=False):
    """Use :obj:`parserestrict.parse_match` to produce a list of matches.

    This matches the restriction against a repo. If multiple pkgs match and a
    simple package name was provided, then the restriction is applied against
    installed repos. If multiple matches still exist then pkgs from the
    'virtual' category are skipped. If multiple pkgs still match the
    restriction, AmbiguousQuery is raised otherwise the matched atom is
    returned. On the other hand, if a globbed match was specified, all repo
    matches are returned.

    :param restriction: string to convert.
    :param repo: :obj:`pkgcore.repository.prototype.tree` instance to search in.
    :param installed_repos: :obj:`pkgcore.config.domain.all_installed_repos`
        instance to search in.
    :param return_none: indicates if no matches raises or returns C{None}

    :return: a list of matches or C{None}.
    """
    key_matches = {x.unversioned_atom for x in repo.itermatch(restriction)}
    if not key_matches:
        if return_none:
            return None
        raise NoMatches(restriction)
    elif len(key_matches) > 1:
        if any(isinstance(r, restricts.PackageDep) for r in iflatten_instance([restriction])):
            if len(restriction) > 1:
                # drop repo specific restrictions, ebuild repos don't match installed pkgs
                restriction = restriction.remove_restriction(
                    restriction_types=(restricts.RepositoryDep,))

            # find installed package matches
            matches = {x.unversioned_atom for x in installed_repos.itermatch(restriction)}

            # try removing stub pkgs if there are multiple installed matches or none at all
            skip_categories = {'acct-group', 'acct-user', 'virtual'}
            if not matches:
                matches = {x for x in key_matches if x.category not in skip_categories}
            elif len(matches) > 1:
                matches = {x for x in matches if x.category not in skip_categories}

            if len(matches) == 1:
                p = matches.pop()
                # TODO: collapse redundant restrictions?
                return [packages.KeyedAndRestriction(restriction, p, key=p.key)]

            raise AmbiguousQuery(restriction, sorted(key_matches))
        else:
            # if a glob was specified then just return every match
            return key_matches
    if isinstance(restriction, atom):
        # atom is guaranteed to be fine, since it's cat/pkg
        return [restriction]
    return [packages.KeyedAndRestriction(restriction, key=key_matches.pop().key)]


@argparser.bind_delayed_default(50, name='world')
def load_world(namespace, attr):
    value = namespace.config.pkgset['world']
    setattr(namespace, attr, value)


def display_pkgsets(out, options):
    for name, kls in sorted(options.config.pkgset.items()):
        if options.verbosity > 0:
            out.write(name)
            out.write('\n'.join('  ' + dedent(x) for x in kls.__doc__.split('\n')))
            out.write()
            if options.verbosity > 1:
                out.write('\n'.join('  ' + str(pkg) for pkg in sorted(kls)))
                out.write()
        else:
            out.write(name)


@argparser.bind_main_func
def main(options, out, err):
    if options.list_sets:
        display_pkgsets(out, options)
        return 0

    config = options.config
    if options.debug:
        resolver.plan.limiters.add(None)

    domain = options.domain
    world_set = world_list = options.world
    if options.oneshot:
        world_set = None

    formatter = options.formatter(
        out=out, err=err,
        unstable_arch=domain.unstable_arch,
        use_expand=domain.profile.use_expand,
        use_expand_hidden=domain.profile.use_expand_hidden,
        pkg_get_use=domain.get_package_use_unconfigured,
        world_list=world_list,
        verbosity=options.verbosity,
        installed_repos=domain.all_installed_repos,
        distdir=domain.fetcher.get_storage_path(),
        quiet_repo_display=options.quiet_repo_display)

    # This mode does not care about sets and packages so bypass all that.
    if options.unmerge:
        if not options.oneshot:
            if world_set is None:
                argparser.error("disable world updating via --oneshot, "
                                "or fix your configuration")
        try:
            unmerge(out, err, domain.installed_repos, options.targets, options, formatter, world_set)
        except (parserestrict.ParseError, Failure) as e:
            argparser.error(e)
        return

    source_repos = domain.source_repos
    installed_repos = domain.installed_repos
    pkg_type = 'ebuilds'

    if options.usepkgonly:
        source_repos = domain.binary_repos
        pkg_type = 'binpkgs'
    elif options.usepkg:
        # binary repos are checked for matches first before ebuild repos
        source_repos = domain.binary_repos + domain.ebuild_repos
        pkg_type = 'ebuilds or binpkgs'
    elif options.source_only:
        source_repos = domain.ebuild_repos

    atoms = []
    for setname, pkgset in options.sets:
        if pkgset is None:
            return 1
        l = list(pkgset)
        if not l:
            out.write(f"skipping set {setname!r}: set is empty, nothing to update")
        else:
            atoms.extend(l)

    for token, restriction in options.targets:
        try:
            matches = parse_target(
                restriction, source_repos.combined, installed_repos, return_none=True)
        except parserestrict.ParseError as e:
            e.token = token
            argparser.error(e)
        if matches is None:
            if not options.ignore_failures:
                error_msg = [f"no matching {pkg_type}: {token!r}"]
                if token in config.pkgset:
                    error_msg.append(f"use '@{token}' instead for the package set")
                elif options.usepkgonly:
                    matches = parse_target(
                        restriction, domain.ebuild_repos.combined,
                        installed_repos, return_none=True)
                    if matches:
                        error_msg.append("try re-running without -K/--usepkgonly "
                                         "enabled to rebuild from source")
                argparser.error(' -- '.join(error_msg))
        else:
            atoms.extend(matches)

    if not atoms and not options.newuse:
        err.write(f"{options.prog}: no targets specified; nothing to do")
        return 1

    atoms = stable_unique(atoms)

    if options.clean and not options.oneshot:
        if world_set is None:
            argparser.error("disable world updating via --oneshot, or fix your configuration")

    extra_kwargs = {}
    if options.empty:
        extra_kwargs['resolver_cls'] = resolver.empty_tree_merge_plan
    if options.debug:
        extra_kwargs['debug'] = True

    # XXX: This should recurse on deep
    if options.newuse:
        out.write(out.bold, ' * ', out.reset, 'Scanning for changed USE...')
        out.title('Scanning for changed USE...')
        for inst_pkg in installed_repos.itermatch(OrRestriction(*atoms)):
            src_pkgs = source_repos.match(inst_pkg.versioned_atom)
            if src_pkgs:
                src_pkg = max(src_pkgs)
                inst_iuse = inst_pkg.iuse_stripped
                src_iuse = src_pkg.iuse_stripped
                inst_flags = inst_iuse.intersection(inst_pkg.use)
                src_flags = src_iuse.intersection(src_pkg.use)
                if inst_flags.symmetric_difference(src_flags) or \
                   inst_iuse.symmetric_difference(src_iuse):
                    atoms.append(src_pkg.unversioned_atom)

    excludes = [restriction for token, restriction in options.excludes]
    if options.onlydeps:
        excludes.extend(atoms)

    if excludes:
        injected_repo = RestrictionRepo(
            repo_id='injected', restrictions=excludes, frozen=True, livefs=True)
        installed_repos = injected_repo + installed_repos

#    left intentionally in place for ease of debugging.
#    from guppy import hpy
#    hp = hpy()
#    hp.setrelheap()

    resolver_inst = options.resolver_kls(
        vdbs=installed_repos, dbs=source_repos,
        verify_vdb=options.deep, nodeps=options.nodeps,
        drop_cycles=options.ignore_cycles, force_replace=options.replace,
        process_built_depends=options.with_bdeps, **extra_kwargs)

    if options.preload_vdb_state:
        out.write(out.bold, ' * ', out.reset, 'Preloading vdb... ')
        vdb_time = time()
        resolver_inst.load_vdb_state()
        vdb_time = time() - vdb_time
    else:
        vdb_time = 0.0

    # flush warning messages before dep resolution begins
    out.flush()
    err.flush()

    failures = []
    resolve_time = time()
    if sys.stdout.isatty():
        out.title('Resolving...')
        out.write(out.bold, ' * ', out.reset, 'Resolving...')
        out.flush()
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
            out.error(f"failed '{restrict}'")
            out.write('potentials:')
            match_count = 0
            for r in get_raw_repos(source_repos):
                l = r.match(restrict)
                if l:
                    out.write(f"repo {r}: [ {', '.join(map(str, l))} ]")
                    match_count += len(l)
            if not match_count:
                out.write("No matches found")
            if not options.ignore_failures:
                return 1
            out.write()

    resolver_inst.free_caches()

    if options.clean:
        out.write(out.bold, ' * ', out.reset, 'Packages to be removed:')
        vset = set(installed_repos.real.combined)
        len_vset = len(vset)
        vset.difference_update(x.pkg for x in resolver_inst.state.iter_ops(True))
        wipes = sorted(x for x in vset if x.package_is_real)
        for x in wipes:
            out.write(f"Remove {x}")
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
        repo_obs = observer.repo_observer(
            observer.formatter_output(out), debug=options.debug)
        do_unmerge(options, out, err, installed_repos.real.combined, wipes, world_set, repo_obs)
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

    build_obs = observer.phase_observer(
        observer.formatter_output(out), debug=options.debug)
    repo_obs = observer.repo_observer(
        observer.formatter_output(out), debug=options.debug)

    # show pkgs to merge in selected format
    if (options.ask or options.pretend) and changes:
        for op in changes:
            formatter.format(op)
        formatter.end()

    if vdb_time:
        out.write(out.bold, 'Took %.2f' % (vdb_time,), out.reset,
                  ' seconds to preload vdb state')

    if changes:
        if not options.fetchonly:
            # run sanity checks for pkgs -- pkg_pretend, REQUIRED_USE, etc
            out.write()
            out.write(out.bold, " * ", out.reset, "Running sanity checks...")
            if options.debug:
                start_time = time()
            # flush output so bash spawned errors are shown in the correct order of events
            out.flush()
            sanity_failures = run_sanity_checks((x.pkg for x in changes), domain, threads=1)
            if sanity_failures:
                for pkg, errors in sanity_failures.items():
                    out.write('\n'.join(e.msg(verbosity=options.verbosity) for e in errors))
                    if options.verbosity > 0:
                        out.write()
                if options.ignore_failures:
                    out.write(
                        out.fg('red'), out.bold, "!!! ",
                        out.reset, "Skipping failed sanity checks...")
                else:
                    out.write(
                        out.fg('red'), out.bold, "!!! ",
                        out.reset, "Sanity checks failed, exiting...")
                    return 1
            else:
                out.write()
            if options.debug:
                out.write(
                    out.bold, " * ", out.reset,
                    "finished sanity checks in %.2f seconds" % (time() - start_time))
                out.write()
    elif options.verbosity > 0:
        # show skipped virtuals
        virtual_pkgs = set()
        for x in atoms:
            matches = installed_repos.virtual.match(x)
            if matches:
                virtual_pkgs.add(sorted(matches)[-1])
        if virtual_pkgs:
            out.write(
                "Skipping virtual pkgs:\n%s\n" % '\n'.join(
                    str(x.versioned_atom) for x in virtual_pkgs))

        out.write("Nothing to merge.")
        return

    if options.pretend:
        if options.verbosity > 0:
            out.write(
                out.bold, ' * ', out.reset,
                "resolver plan required %i ops (%.2f seconds)" %
                (len(resolver_inst.state.plan), resolve_time))
        return

    action = 'merge'
    if options.fetchonly:
        action = 'fetch'
    if (options.ask and not formatter.ask(f"Would you like to {action} these packages?")):
        return

    change_count = len(changes)

    # left in place for ease of debugging.
    cleanup = []
    try:
        for count, op in enumerate(changes):
            for func in cleanup:
                func()

            cleanup = []

            out.write(f"\nProcessing {count + 1} of {change_count}: "
                      f"{op.pkg.cpvstr}::{op.pkg.repo}")
            out.title(f"{count + 1}/{change_count}: {op.pkg.cpvstr}")
            if op.desc != "remove":
                cleanup.append(op.pkg.release_cached_data)

                if not options.fetchonly and options.debug:
                    out.write("Forcing a clean of workdir")

                pkg_ops = domain.pkg_operations(op.pkg, observer=build_obs)
                out.write(f"\n{len(op.pkg.distfiles)} file{pluralism(op.pkg.distfiles)} required-")
                if not pkg_ops.run_if_supported("fetch", or_return=True):
                    out.error(f"fetching failed for {op.pkg.cpvstr}")
                    if not options.ignore_failures:
                        return 1
                    continue
                if options.fetchonly:
                    continue

                buildop = pkg_ops.run_if_supported("build", or_return=None)
                pkg = op.pkg
                if buildop is not None:
                    out.write(f"building {op.pkg.cpvstr}")
                    result = False
                    exc = None
                    try:
                        result = buildop.finalize()
                    except format.BuildError as e:
                        out.error(f"caught exception building {op.pkg.cpvstr}: {e}")
                        exc = e
                    else:
                        if result is False:
                            out.error(f"failed building {op.pkg.cpvstr}")
                    if result is False:
                        if not options.ignore_failures:
                            raise ExitException(1) from exc
                        continue
                    pkg = result
                    cleanup.append(pkg.release_cached_data)
                    pkg_ops = domain.pkg_operations(pkg, observer=build_obs)
                    cleanup.append(buildop.cleanup)

                cleanup.append(partial(pkg_ops.run_if_supported, "cleanup"))
                pkg = pkg_ops.run_if_supported("localize", or_return=pkg)
                # wipe this to ensure we don't inadvertantly use it further down;
                # we aren't resetting it after localizing, so could have the wrong
                # set of ops.
                del pkg_ops

                out.write()
                if op.desc == "replace":
                    if op.old_pkg == pkg:
                        out.write(f">>> Reinstalling {pkg.cpvstr}")
                    else:
                        out.write(f">>> Replacing {op.old_pkg.cpvstr} with {pkg.cpvstr}")
                    i = domain.replace_pkg(op.old_pkg, pkg, repo_obs)
                    cleanup.append(op.old_pkg.release_cached_data)
                else:
                    out.write(f">>> Installing {pkg.cpvstr}")
                    i = domain.install_pkg(pkg, repo_obs)

                # force this explicitly- can hold onto a helluva lot more
                # then we would like.
            else:
                out.write(f">>> Removing {op.pkg.cpvstr}")
                i = domain.uninstall_pkg(op.pkg, repo_obs)
            try:
                ret = i.finish()
            except merge_errors.BlockModification as e:
                out.error(f"Failed to merge {op.pkg}: {e}")
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
                    out.write(f'>>> Removing {op.pkg.cpvstr} from world file')
                    removal_pkg = slotatom_if_slotted(
                        source_repos.combined, op.pkg.versioned_atom)
                    update_worldset(world_set, removal_pkg, remove=True)
                elif not options.oneshot and any(x.match(op.pkg) for x in atoms):
                    if not (options.upgrade or options.downgrade):
                        out.write(f'>>> Adding {op.pkg.cpvstr} to world file')
                        add_pkg = slotatom_if_slotted(
                            source_repos.combined, op.pkg.versioned_atom)
                        update_worldset(world_set, add_pkg)


#    again... left in place for ease of debugging.
#    except KeyboardInterrupt:
#        import pdb;pdb.set_trace()
#    else:
#        import pdb;pdb.set_trace()
    finally:
        pass

    # the final run from the loop above doesn't invoke cleanups;
    # we could ignore it, but better to run it to ensure nothing is
    # inadvertantly held on the way out of this function.
    # makes heappy analysis easier if we're careful about it.
    for func in cleanup:
        func()

    # and wipe the reference to the functions to allow things to fall out of
    # memory.
    cleanup = []

    return 0
