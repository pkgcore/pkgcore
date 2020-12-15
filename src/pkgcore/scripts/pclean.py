"""system cleaning utility"""

import argparse
import errno
import glob
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from functools import partial
from itertools import chain

from snakeoil.mappings import DictMixin
from snakeoil.osutils import listdir_dirs, listdir_files, pjoin
from snakeoil.sequences import iflatten_instance, split_negations
from snakeoil.strings import pluralism

from ..ebuild import atom as atom_mod
from ..ebuild.domain import domain as domain_cls
from ..repository import multiplex
from ..repository.util import SimpleTree, get_virtual_repos
from ..restrictions import boolean, packages
from ..util import parserestrict
from ..util.commandline import (ArgumentParser, StoreRepoObject,
                                convert_to_restrict)

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
            f"invalid date: {s!r} (valid units: {' ,'.join(units.keys())})")
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
            f"invalid size: {s!r} (valid units: {' ,'.join(units.keys())})")
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


class _UnfilteredRepos(DictMixin):
    """Generate custom, unfiltered repos on demand."""

    _supported_attrs = {
        'pkg_masks', 'pkg_unmasks', 'pkg_accept_keywords', 'pkg_keywords',
    }

    def __init__(self, domain):
        self.domain = domain
        self.unfiltered_repos = {}

    def __getitem__(self, key):
        if key not in self._supported_attrs:
            raise KeyError

        try:
            return self.unfiltered_repos[key]
        except KeyError:
            repos = []
            kwargs = {key: ()}
            for repo in self.domain.ebuild_repos_unfiltered:
                repos.append(self.domain.filter_repo(repo, **kwargs))
            unfiltered_repo = multiplex.tree(*repos)
            self.unfiltered_repos[key] = unfiltered_repo
            return unfiltered_repo

    def keys(self):
        return self.unfiltered_repo.keys()

    def values(self):
        return self.unfiltered_repo.values()

    def items(self):
        return self.unfiltered_repo.items()


config = subparsers.add_parser(
   'config', parents=(shared_opts,),
   description='remove config file settings')
@config.bind_main_func
def config_main(options, out, err):
    domain = options.domain
    installed_repos = domain.all_installed_repos
    all_repos_raw = domain.all_repos_raw
    all_ebuild_repos = domain.all_ebuild_repos

    # proxy to create custom, unfiltered repos
    unfiltered_repos = _UnfilteredRepos(domain)

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
        # call jitted attr funcs directly to provide debug data
        func = getattr(domain_cls, name).function
        # filter excluded, matching restricts from the data stream
        attrs[name] = iter_restrict(func(domain, debug=True))

    changes = defaultdict(lambda: defaultdict(list))
    for name, iterable in attrs.items():
        for restrict, item in iterable:
            path, lineno, line = item.pop(), item.pop(), item.pop()
            if not all_repos_raw.match(restrict):
                changes['unavailable'][path].append((line, lineno, str(restrict)))
                continue

            if not installed_repos.match(restrict):
                changes['uninstalled'][path].append((line, lineno, str(restrict)))

            if name in unfiltered_repos:
                filtered_pkgs = all_ebuild_repos.match(restrict)
                unfiltered_pkgs = unfiltered_repos[name].match(restrict)
                if filtered_pkgs == unfiltered_pkgs:
                    changes[f'unnecessary_{name}'][path].append((line, lineno, str(restrict)))
            elif name == 'pkg_use':
                atom, use = item

                # find duplicates
                use_sets = [set(), set()]
                disabled, enabled = use_sets
                duplicates = set()
                for i, data in enumerate(split_negations(use)):
                    for u in data:
                        if u in use_sets[i]:
                            duplicates.add(u)
                        use_sets[i].add(u)
                if duplicates:
                    changes['duplicate_use'][path].append(
                        (line, lineno, ', '.join(duplicates)))

                # find conflicts
                conflicting = enabled & disabled
                if conflicting:
                    changes['conflicting_use'][path].append(
                        (line, lineno, ', '.join(conflicting)))

                # find unknowns
                pkgs = all_repos_raw.match(atom)
                available = {u for pkg in pkgs for u in pkg.iuse_stripped}
                unknown = (disabled - available) | (enabled - available)
                if unknown:
                    changes['unknown_use'][path].append(
                        (line, lineno, ', '.join(unknown)))

    type_mapping = {
        'unavailable': 'Unavailable package(s)',
        'uninstalled': 'Uninstalled package(s)',
        'unnecessary_pkg_masks': 'Unnecessary mask(s)',
        'unnecessary_pkg_unmasks': 'Unnecessary unmask(s)',
        'unnecessary_pkg_accept_keywords': 'Unnecessary accept keywords(s)',
        'unnecessary_pkg_keywords': 'Unnecessary keywords(s)',
        'duplicate_use': 'Duplicate use flag(s)',
        'conflicting_use': 'Conflicting use flag(s)',
        'unknown_use': 'Nonexistent use flag(s)',
    }

    for t, paths in changes.items():
        out.write(f"{type_mapping[t]}:")
        for path, data in paths.items():
            out.write(f"{path}:", prefix="  ")
            for line, lineno, values in data:
                out.write(f"{values} -- line {lineno}: {line!r}", prefix="    ")
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
            pn_regex = r'\W'.join(re.split(r'\W', catpn.package))
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


def pkg_changed(pkg, domain, attrs):
    """Determine if given attributes from a binpkg changed compared to the related ebuild."""
    try:
        repo = domain.ebuild_repos_raw[pkg.source_repository]
        ebuild_pkg = repo.match(pkg.versioned_atom)[0]
    except (KeyError, IndexError):
        # source repo doesn't exist on the system or related ebuild doesn't exist
        return False
    for attr in attrs:
        try:
            ebuild_attr = getattr(ebuild_pkg, attr)
            binpkg_attr = getattr(pkg, attr)
        except AttributeError:
            raise argparser.error(f'nonexistent attribute: {attr!r}')
        if attr.upper() in pkg.eapi.dep_keys:
            ebuild_attr = ebuild_attr.evaluate_depset(pkg.use)
        if ebuild_attr != binpkg_attr:
            return True
    return False


pkg_opts = ArgumentParser(suppress=True)
pkg_cleaning_opts = pkg_opts.add_argument_group('binpkg cleaning options')
pkg_cleaning_opts.add_argument(
    '--source-repo', metavar='REPO',
    help='remove binpkgs with matching source repo')
pkg_cleaning_opts.add_argument(
    '-b', '--bindist', action='store_true',
    help='only remove binpkgs that restrict distribution')
pkg_cleaning_opts.add_argument(
    '-c', '--changed', action='csv',
    help='comma separated list of package attributes to check for ebuild changes')
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
    if namespace.changed:
        pkg_filters.append(lambda pkg: pkg_changed(pkg, namespace.domain, namespace.changed))
    if namespace.exclude_installed:
        pkg_filters.append(lambda pkg: pkg.versioned_atom not in namespace.domain.all_installed_repos)
    if namespace.exclude_exists:
        pkg_filters.append(lambda pkg: pkg.versioned_atom not in namespace.domain.all_ebuild_repos_raw)
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
            if options.pretend and options.verbosity >= 0:
                out.write(f"Would remove {target}")
            elif options.verbosity > 0:
                out.write(f"Removing {target}")
            try:
                if not options.pretend:
                    func(target)
            except OSError as e:
                if options.verbosity >= 0:
                    err.write(f"{options.prog}: failed to remove {target!r}: {e.strerror}")
                ret = 1
                continue
    else:
        out.write('\n'.join(target for _, target in options.remove))
    return ret


class Filters:
    """Generic filtering support."""

    def __init__(self):
        self._filters = []

    def append(self, f):
        self._filters.append(f)

    @property
    def run(self):
        """Run a given object through all registered filters."""
        return lambda x: all(f(x) for f in self._filters)
