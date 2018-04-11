# Copyright: 2015-2016 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

"""system cleaning utility"""

import argparse
from collections import defaultdict
from itertools import chain
import os
import sys

from snakeoil.demandload import demandload
from snakeoil.strings import pluralism

from pkgcore.restrictions import boolean, packages
from pkgcore.repository import multiplex
from pkgcore.repository.util import get_virtual_repos
from pkgcore.util.commandline import ArgumentParser, StoreRepoObject, convert_to_restrict

demandload(
    'errno',
    'functools:partial',
    'glob',
    're',
    'time',
    'shutil',
    'snakeoil:klass',
    'snakeoil.osutils:listdir_dirs,listdir_files,pjoin',
    'snakeoil.sequences:iflatten_instance,split_negations',
    'pkgcore:fetch',
    'pkgcore.ebuild:atom@atom_mod',
    'pkgcore.package:errors',
    'pkgcore.repository.util:SimpleTree',
    'pkgcore.util:parserestrict',
)


argparser = ArgumentParser(description=__doc__, script=(__file__, __name__))
subparsers = argparser.add_subparsers(description='cleaning applets')
@argparser.bind_parse_priority(10)
def _initialize_opts(namespace):
    namespace.restrict = []
    namespace.file_filters = Filters()

shared_opts = ArgumentParser(suppress=True)
cleaning_opts = shared_opts.add_argument_group('generic cleaning options')
cleaning_opts.add_argument(
    nargs='*', dest='targets', metavar='TARGET',
    help="packages to target for cleaning")
cleaning_opts.add_argument(
    '-p', '--pretend', action='store_true',
    help='dry run without performing any changes')
cleaning_opts.add_argument(
    '-x', '--exclude', action='csv', dest='excludes', metavar='EXCLUDE',
    help='list of packages to exclude from removal')
cleaning_opts.add_argument(
    '-X', '--exclude-file', type=argparse.FileType('r'),
    help='path to exclusion file')
cleaning_opts.add_argument(
    '-S', '--pkgsets', action='csv_negations', metavar='PKGSET',
    help='list of pkgsets to include or exclude from removal')
@shared_opts.bind_parse_priority(20)
def _setup_shared_opts(namespace):
    namespace.exclude_restrict = None
    exclude_restrictions = []

    if namespace.pkgsets:
        disabled, enabled = namespace.pkgsets
        unknown_sets = set(disabled + enabled).difference(namespace.config.pkgset)
        if unknown_sets:
            argparser.error("unknown set%s: %s (available sets: %s)" % (
                pluralism(unknown_sets),
                ', '.join(sorted(map(repr, unknown_sets))),
                ', '.join(sorted(namespace.config.pkgset))))
        for s in set(disabled):
            exclude_restrictions.extend(namespace.config.pkgset[s])
        for s in set(enabled):
            namespace.restrict.append(boolean.OrRestriction(*namespace.config.pkgset[s]))

    # handle command line and file excludes
    excludes = namespace.excludes if namespace.excludes is not None else []
    if namespace.exclude_file is not None:
        excludes.extend(namespace.exclude_file.read().split('\n'))
    if excludes:
        exclude_restrictions.extend(convert_to_restrict(excludes, default=None))

    if exclude_restrictions:
        namespace.restrict.append(
            boolean.OrRestriction(negate=True, *exclude_restrictions))
        namespace.exclude_restrict = boolean.OrRestriction(*exclude_restrictions)


def parse_time(s):
    # simple approximations, could use dateutil for exact deltas
    units = {'s': 1}
    units['min'] = units['s'] * 60
    units['h'] = units['min'] * 60
    units['d'] = units['h'] * 24
    units['w'] = units['d'] * 7
    units['m'] = units['d'] * 30
    units['y'] = units['d'] * 365

    date = re.match(r'^(\d+)(%s)$' % '|'.join(units.keys()), s)
    if date:
        value = int(date.group(1))
        unit = date.group(2)
    else:
        raise argparse.ArgumentTypeError(
            "invalid date: %r (valid units: %s)" % (s, ', '.join(units.keys())))
    return time.time() - (value * units[unit])


def parse_size(s):
    units = {
        'B': 1,
        'K': 1024,
        'M': 1024**2,
        'G': 1024**3,
    }

    size = re.match(r'^(\d+)([%s])$' % ''.join(units.keys()), s)
    if size:
        value = int(size.group(1))
        unit = size.group(2)
    else:
        raise argparse.ArgumentTypeError(
            "invalid size: %r (valid units: %s)" % (s, ', '.join(units.keys())))
    return value * units[unit]


file_opts = ArgumentParser(suppress=True)
file_cleaning_opts = file_opts.add_argument_group('file cleaning options')
file_cleaning_opts.add_argument(
    '-m', '--modified', metavar='TIME', type=parse_time,
    help='skip files that have been modified since a given time',
    docs="""
        Don't remove files that have been modified since a given time. For
        example, to skip files newer than a year use "1y" as an argument to this
        option.  this option.

        Supported units are y, m, w, and d, and s representing years, months,
        weeks, days, and seconds, respectively.
    """)
file_cleaning_opts.add_argument(
    '-s', '--size', metavar='SIZE', type=parse_size,
    help='skip files bigger than a given size',
    docs="""
        Don't remove files bigger than a given size.  For example, to skip
        files larger than 100 megabytes use "100M" as an argument to this
        option.

        Supported units are B, K, M, and G representing bytes, kilobytes,
        megabytes, and gigabytes, respectively.
    """)
@file_opts.bind_parse_priority(20)
def _setup_file_opts(namespace):
    if namespace.modified is not None:
        namespace.file_filters.append(lambda x: os.stat(x).st_mtime < namespace.modified)
    if namespace.size is not None:
        namespace.file_filters.append(lambda x: os.stat(x).st_size < namespace.size)


repo_opts = ArgumentParser(suppress=True)
repo_cleaning_opts = repo_opts.add_argument_group('repo cleaning options')
repo_cleaning_opts.add_argument(
    '-I', '--installed', action='store_true', dest='exclude_installed',
    help='skip files for packages that are currently installed')
repo_cleaning_opts.add_argument(
    '-E', '--exists', action='store_true', dest='exclude_exists',
    help='skip files for packages that relate to ebuilds in the tree')
repo_cleaning_opts.add_argument(
    '-f', '--fetch-restricted', action='store_true', dest='exclude_fetch_restricted',
    help='skip fetch-restricted files')
repo_cleaning_opts.add_argument(
    "-r", "--repo", help="target repository",
    action=StoreRepoObject,
    docs="""
        Target repository to search for matches. If no repo is specified all
        relevant repos are used.
    """)


@argparser.bind_parse_priority(30)
def _setup_restrictions(namespace):
    repo = namespace.domain.all_source_repos_raw
    target_restrictions = []

    # If no targets are passed, create a restriction from the current working
    # directory if inside a known repo.
    cwd = os.getcwd()
    if not namespace.targets and cwd in repo:
        namespace.targets = [cwd]

    for target in namespace.targets:
        try:
            target_restrictions.append(parserestrict.parse_match(target))
        except parserestrict.ParseError as e:
            if os.path.exists(target):
                try:
                    restrict = repo.path_restrict(target)
                    # toss the repo restriction, keep the rest
                    target_restrictions.append(boolean.AndRestriction(*restrict[1:]))
                except ValueError as e:
                    argparser.error(e)
            else:
                argparser.error(e)

    if target_restrictions:
        namespace.restrict.append(boolean.OrRestriction(*target_restrictions))
    if namespace.restrict:
        namespace.restrict = boolean.AndRestriction(*namespace.restrict)


config = subparsers.add_parser(
   'config', parents=(shared_opts,),
   description='remove config file settings')
@config.bind_final_check
def _config_finalize_args(parser, namespace):
    # enable debug output (line/lineno/path data) for config data
    namespace.domain._debug = True


@config.bind_main_func
def config_main(options, out, err):
    installed_repos = options.domain.all_installed_repos
    all_repos_raw = options.domain.all_repos_raw
    domain = options.domain

    def iter_restrict(iterable):
        for x in iterable:
            restrict = x[0]
            if (options.exclude_restrict is None or
                    not options.exclude_restrict.match(restrict)):
                yield restrict, list(x)

    domain_attrs = (
        'pkg_masks', 'pkg_unmasks', 'pkg_keywords', 'pkg_accept_keywords',
        'pkg_licenses', 'pkg_use', 'pkg_env',
    )

    attrs = {}
    for name in domain_attrs:
        # force JIT-ed attr refresh to provide debug data
        setattr(domain, '_jit_' + name, klass._singleton_kls)
        # filter excluded, matching restricts from the data stream
        attrs[name] = iter_restrict(getattr(domain, name))

    changes = defaultdict(list)
    for name, iterable in attrs.items():
        for restrict, item in iterable:
            path, lineno, line = item.pop(), item.pop(), item.pop()
            if not installed_repos.match(restrict):
                changes['uninstalled'].append((path, line, lineno, str(restrict)))
            if name == 'pkg_use':
                atom, use = item
                disabled, enabled = split_negations(use)
                pkgs = all_repos_raw.match(atom)
                available = {u for pkg in pkgs for u in pkg.iuse_stripped}
                unknown_disabled = set(disabled) - available
                unknown_enabled = set(enabled) - available
                if unknown_disabled:
                    changes['unknown_use'].append((
                        path, line, lineno, ' '.join('-' + u for u in unknown_disabled)))
                if unknown_enabled:
                    changes['unknown_use'].append(
                        (path, line, lineno, ' '.join(unknown_enabled)))

    type_mapping = {
        'uninstalled': 'Uninstalled package',
        'unknown_use': 'Nonexistent use flag(s)',
    }

    for type, data in changes.items():
        out.write(f"{type_mapping[type]}:")
        for path, line, lineno, values in data:
            out.write(f"{path}:")
            out.write(f"{values} -- line {lineno}: {line!r}")
            out.write()


dist = subparsers.add_parser(
    'dist', parents=(shared_opts, file_opts, repo_opts),
    description='remove distfiles')
dist_opts = dist.add_argument_group('distfile options')
@dist.bind_final_check
def _dist_validate_args(parser, namespace):
    distdir = namespace.domain.fetcher.distdir
    repo = namespace.repo
    if repo is None:
        repo = multiplex.tree(*get_virtual_repos(namespace.domain.source_repos, False))

    all_dist_files = set(os.path.basename(f) for f in listdir_files(distdir))
    target_files = set()
    installed_dist = set()
    exists_dist = set()
    excludes_dist = set()
    restricted_dist = set()

    # exclude distfiles used by installed packages -- note that this uses the
    # distfiles attr with USE settings bound to it
    if namespace.exclude_installed:
        for pkg in namespace.domain.all_installed_repos:
            installed_dist.update(iflatten_instance(pkg.distfiles))

    # exclude distfiles for existing ebuilds or fetch restrictions
    if namespace.exclude_fetch_restricted or (namespace.exclude_exists and not namespace.restrict):
        for pkg in repo:
            exists_dist.update(iflatten_instance(getattr(pkg, '_raw_pkg', pkg).distfiles))
            if 'fetch' in pkg.restrict:
                restricted_dist.update(iflatten_instance(getattr(pkg, '_raw_pkg', pkg).distfiles))

    # exclude distfiles from specified restrictions
    if namespace.exclude_restrict:
        for pkg in repo.itermatch(namespace.exclude_restrict, sorter=sorted):
            excludes_dist.update(iflatten_instance(getattr(pkg, '_raw_pkg', pkg).distfiles))

    # determine dist files for custom restrict targets
    if namespace.restrict:
        target_dist = defaultdict(lambda: defaultdict(set))
        for pkg in repo.itermatch(namespace.restrict, sorter=sorted):
            s = set(iflatten_instance(getattr(pkg, '_raw_pkg', pkg).distfiles))
            target_dist[pkg.unversioned_atom][pkg].update(s)
            if namespace.exclude_exists:
                exists_dist.update(s)

        extra_regex_prefixes = defaultdict(set)
        pkg_regex_prefixes = set()
        for catpn, pkgs in target_dist.items():
            pn_regex = '\W'.join(re.split(r'\W', catpn.package))
            pkg_regex = re.compile(r'(%s)(\W\w+)+([\W?(0-9)+])*(\W\w+)*(\.\w+)*' % pn_regex,
                                   re.IGNORECASE)
            pkg_regex_prefixes.add(pn_regex)
            for pkg, files in pkgs.items():
                files = sorted(files)
                for f in files:
                    if (pkg_regex.match(f) or (
                            extra_regex_prefixes and
                            re.match(r'(%s)([\W?(0-9)+])+(\W\w+)*(\.\w+)+' % '|'.join(extra_regex_prefixes[catpn]), f))):
                        continue
                    else:
                        pieces = re.split(r'([\W?(0-9)+])+(\W\w+)*(\.\w+)+', f)
                        if pieces[-1] == '':
                            pieces.pop()
                        if len(pieces) > 1:
                            extra_regex_prefixes[catpn].add(pieces[0])

        if target_dist:
            regexes = []
            # build regexes to match distfiles for older ebuilds no longer in the tree
            if pkg_regex_prefixes:
                pkg_regex_prefixes_str = '|'.join(sorted(pkg_regex_prefixes))
                regexes.append(re.compile(r'(%s)(\W\w+)+([\W?(0-9)+])*(\W\w+)*(\.\w+)*' % (
                    pkg_regex_prefixes_str,)))
            if extra_regex_prefixes:
                extra_regex_prefixes_str = '|'.join(sorted(chain.from_iterable(
                    v for k, v in extra_regex_prefixes.items())))
                regexes.append(re.compile(r'(%s)([\W?(0-9)+])+(\W\w+)*(\.\w+)+' % (
                    extra_regex_prefixes_str,)))

            if regexes:
                for f in all_dist_files:
                    if any(r.match(f) for r in regexes):
                        target_files.add(f)
    else:
        target_files = all_dist_files

    # exclude files tagged for saving
    saving_files = installed_dist | exists_dist | excludes_dist | restricted_dist
    target_files.difference_update(saving_files)

    targets = (pjoin(distdir, f) for f in sorted(all_dist_files.intersection(target_files)))
    removal_func = partial(os.remove)
    namespace.remove = (
        (removal_func, f) for f in
        filter(namespace.file_filters.run, targets))


pkg_opts = ArgumentParser(suppress=True)
pkg_cleaning_opts = pkg_opts.add_argument_group('binpkg cleaning options')
pkg_cleaning_opts.add_argument(
    '--source-repo', metavar='REPO',
    help='remove binpkgs with matching source repo')
pkg_cleaning_opts.add_argument(
    '-b', '--bindist', action='store_true',
    help='only remove binpkgs that restrict distribution')
pkg = subparsers.add_parser(
    'pkg', parents=(shared_opts, file_opts, repo_opts, pkg_opts),
    description='remove binpkgs')
@pkg.bind_final_check
def _pkg_validate_args(parser, namespace):
    repo = namespace.repo
    if repo is None:
        repo = namespace.domain.all_binary_repos

    if not namespace.restrict:
        # not in a configured repo dir, remove all binpkgs
        namespace.restrict = packages.AlwaysTrue

    pkgs = (pkg for pkg in repo.itermatch(namespace.restrict))
    pkg_filters = Filters()
    if namespace.bindist:
        pkg_filters.append(lambda pkg: 'bindist' in pkg.restrict)
    if namespace.exclude_installed:
        pkg_filters.append(lambda pkg: pkg.versioned_atom not in namespace.all_installed_repos)
    if namespace.exclude_fetch_restricted:
        pkg_filters.append(lambda pkg: 'fetch' not in pkg.restrict)
    if namespace.source_repo is not None:
        pkg_filters.append(lambda pkg: namespace.source_repo == pkg.source_repository)
    pkgs = list(filter(pkg_filters.run, pkgs))
    removal_func = partial(os.remove)
    namespace.remove = (
        (removal_func, binpkg) for binpkg in
        sorted(filter(namespace.file_filters.run, (pkg.path for pkg in pkgs))))

tmp = subparsers.add_parser(
    'tmp', parents=(shared_opts,),
    description='remove tmpdir entries')
tmp_opts = tmp.add_argument_group('tmpfile options')
tmp_opts.add_argument(
    '-a', '--all', dest='wipe_all', action='store_true',
    help='wipe the entire tmpdir',
    docs="""
        Force the entire tmpdir to be wiped. Note that this overrides any
        restrictions that have been specified.
    """)
@tmp.bind_final_check
def _tmp_validate_args(parser, namespace):
    tmpdir = namespace.domain.pm_tmpdir
    dirs = ()
    files = ()

    if namespace.restrict and not namespace.wipe_all:
        # create a fake repo from tmpdir entries and pull matches from it
        pkg_map = {}
        for pkg_build_dir in glob.glob(pjoin(tmpdir, '*', '*')):
            try:
                pkg = atom_mod.atom('=' + pkg_build_dir[len(tmpdir):].lstrip(os.path.sep))
            except atom_mod.MalformedAtom:
                continue
            pkg_map.setdefault(pkg.category, {}).setdefault(pkg.package, []).append(pkg.fullver)
        repo = SimpleTree(pkg_map)

        def _remove_dir_and_empty_parent(d):
            """Remove a given directory tree and its parent directory, if empty."""
            shutil.rmtree(d)
            try:
                os.rmdir(os.path.dirname(d))
            except OSError as e:
                # POSIX specifies either ENOTEMPTY or EEXIST for non-empty dir
                # in particular, Solaris uses EEXIST in that case.
                if e.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise

        removal_func = partial(_remove_dir_and_empty_parent)
        dirs = ((removal_func, pjoin(tmpdir, pkg.cpvstr))
                for pkg in repo.itermatch(namespace.restrict))
    else:
        # not in a configured repo dir, remove all tmpdir entries
        dir_removal_func = partial(shutil.rmtree)
        dirs = ((dir_removal_func, pjoin(tmpdir, d)) for d in listdir_dirs(tmpdir))
        file_removal_func = partial(os.remove)
        files = ((file_removal_func, pjoin(tmpdir, f)) for f in listdir_files(tmpdir))

    namespace.remove = chain(dirs, files)


@dist.bind_main_func
@pkg.bind_main_func
@tmp.bind_main_func
def _remove(options, out, err):
    """Generic removal runner."""
    ret = 0
    if sys.stdout.isatty():
        # TODO: parallelize this
        for func, target in options.remove:
            if options.pretend and not options.quiet:
                out.write(f"Would remove {target}")
            elif options.verbose:
                out.write(f"Removing {target}")
            try:
                if not options.pretend:
                    func(target)
            except OSError as e:
                if options.verbose or not options.quiet:
                    err.write(f"{options.prog}: failed to remove {target!r}: {e.strerror}")
                ret = 1
                continue
    else:
        out.write('\n'.join(target for _, target in options.remove))
    return ret


class Filters(object):
    """Generic filtering support."""

    def __init__(self):
        self._filters = []

    def append(self, f):
        self._filters.append(f)

    @property
    def run(self):
        """Run a given object through all registered filters."""
        return lambda x: all(f(x) for f in self._filters)
