# Copyright: 2015-2016 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

"""system cleaning utility"""

import argparse
from itertools import chain, ifilter
import os

from snakeoil.demandload import demandload

from pkgcore.restrictions import boolean, packages
from pkgcore.repository import multiplex
from pkgcore.util import commandline
from pkgcore.util.repo_utils import get_virtual_repos

demandload(
    'errno',
    'functools:partial',
    'glob',
    're',
    'time',
    'shutil',
    'snakeoil.osutils:listdir_dirs,listdir_files,pjoin',
    'snakeoil.sequences:iflatten_instance',
    'pkgcore:fetch',
    'pkgcore.ebuild:atom',
    'pkgcore.package:errors',
    'pkgcore.repository.util:SimpleTree',
    'pkgcore.util:parserestrict',
)


argparser = commandline.ArgumentParser(description=__doc__)
subparsers = argparser.add_subparsers(description='cleaning applets')
@argparser.bind_delayed_default(10)
def _initialize_opts(namespace, attr):
    namespace.restrict = []
    namespace.filters = Filters()

shared_opts = commandline.ArgumentParser(suppress=True)
cleaning_opts = shared_opts.add_argument_group('generic cleaning options')
cleaning_opts.add_argument(
    nargs='*', dest='targets', metavar='TARGET',
    help="packages to target for cleaning")
cleaning_opts.add_argument(
    '-p', '--pretend', action='store_true',
    help='dry run without performing any changes')
cleaning_opts.add_argument(
    '-x', '--exclude', action='extend_comma', dest='excludes',
    help='list of packages to exclude from removal')
cleaning_opts.add_argument(
    '-X', '--exclude-file', type=argparse.FileType('r'),
    help='path to exclusion file')
@shared_opts.bind_delayed_default(20, 'shared_opts')
def _setup_shared_opts(namespace, attr):
    # handle command line and file excludes
    excludes = namespace.excludes if namespace.excludes is not None else []
    if namespace.exclude_file is not None:
        excludes.extend(namespace.exclude_file.read().split('\n'))
    exclude_restrictions = commandline.convert_to_restrict(excludes, default=None)

    if exclude_restrictions != [None]:
        namespace.restrict.append(
            boolean.OrRestriction(negate=True, *exclude_restrictions))


def parse_time(s):
    # simple approximations, could use dateutil for exact deltas
    units = {'s': 60}
    units['h'] = units['s'] * 60
    units['d'] = units['h'] * 24
    units['w'] = units['d'] * 7
    units['m'] = units['d'] * 30
    units['y'] = units['d'] * 365

    date = re.match(r'^(\d+)([%s])$' % ''.join(units.keys()), s)
    if date:
        value = int(date.group(1))
        unit = date.group(2)
    else:
        raise argparse.ArgumentTypeError('invalid date: ' + s)
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
        raise argparse.ArgumentTypeError('invalid size: ' + s)
    return value * units[unit]


file_opts = commandline.ArgumentParser(suppress=True)
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
@file_opts.bind_delayed_default(20, 'file_opts')
def _setup_file_opts(namespace, attr):
    if namespace.modified is not None:
        namespace.filters.append(lambda x: os.stat(x).st_mtime < namespace.modified)
    if namespace.size is not None:
        namespace.filters.append(lambda x: os.stat(x).st_size < namespace.size)


repo_opts = commandline.ArgumentParser(suppress=True)
repo_cleaning_opts = repo_opts.add_argument_group('repo cleaning options')
repo_cleaning_opts.add_argument(
    '-I', '--installed', action='store_true',
    help='skip files for packages that are currently installed')
repo_cleaning_opts.add_argument(
    '-f', '--fetch-restricted', action='store_true',
    help='skip fetch-restricted files')
@repo_opts.bind_delayed_default(20, 'repo_opts')
def _setup_repo_opts(namespace, attr):
    if namespace.installed:
        namespace.installed = namespace.domain.all_livefs_repos


@argparser.bind_delayed_default(30, 'restrictions')
def _setup_restrictions(namespace, attr):
    repo = namespace.domain.all_repos
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


# TODO: add config support
#config = subparsers.add_parser(
#    'config', parents=(shared_opts,),
#    description='remove config file settings')
#@config.bind_main_func
#def config_main(options, out, err):
#    pass


dist = subparsers.add_parser(
    'dist', parents=(shared_opts, file_opts, repo_opts),
    description='remove distfiles')
dist_opts = dist.add_argument_group('distfile options')
dist_opts.add_argument(
    '-i', '--ignore-failures', action='store_true',
    help='ignore checksum parsing errors')
@dist.bind_final_check
def _dist_validate_args(parser, namespace):
    distdir = namespace.domain.fetcher.distdir
    repo = multiplex.tree(*get_virtual_repos(namespace.domain.repos, False))
    if not namespace.restrict:
        namespace.restrict = packages.AlwaysTrue

    files = set(os.path.basename(f) for f in listdir_files(distdir))
    pfiles = set()

    for pkg in repo.itermatch(namespace.restrict, sorter=sorted):
        if ((namespace.installed and pkg.versioned_atom in namespace.installed) or
                (namespace.fetch_restricted and 'fetch' in pkg.restrict)):
            continue
        try:
            pfiles.update(
                fetchable.filename for fetchable in
                iflatten_instance(pkg.fetchables, fetch.fetchable))
        except errors.MetadataException as e:
            if not namespace.ignore_failures:
                dist.error(
                    "got corruption error '%s', with package %s " %
                    (e, pkg.cpvstr))
        except Exception as e:
            dist.error(
                "got error '%s', parsing package %s in repo '%s'" %
                (e, pkg.cpvstr, pkg.repo))

    distfiles = (pjoin(distdir, f) for f in files.intersection(pfiles))
    removal_func = partial(os.remove)
    namespace.remove = (
        (removal_func, distfile) for distfile in
        ifilter(namespace.filters.run, distfiles))


pkg_opts = commandline.ArgumentParser(suppress=True)
pkg_cleaning_opts = pkg_opts.add_argument_group('binpkg cleaning options')
pkg_cleaning_opts.add_argument(
    '--source-repo', metavar='REPO',
    help='remove binpkgs with matching source repo')
pkg = subparsers.add_parser(
    'pkg', parents=(shared_opts, file_opts, repo_opts, pkg_opts),
    description='remove binpkgs')
@pkg.bind_final_check
def _pkg_validate_args(parser, namespace):
    repo = namespace.domain.all_binary_repos

    if not namespace.restrict:
        # not in a configured repo dir, remove all binpkgs
        namespace.restrict = packages.AlwaysTrue

    pkgs = set(pkg for pkg in repo.itermatch(namespace.restrict))
    if namespace.installed:
        pkgs = (pkg for pkg in pkgs if pkg.versioned_atom not in namespace.installed)
    if namespace.fetch_restricted:
        pkgs = (pkg for pkg in pkgs if 'fetch' not in pkg.restrict)
    if namespace.source_repo is not None:
        pkgs = (pkg for pkg in pkgs if namespace.source_repo == pkg.source_repository)
    removal_func = partial(os.remove)
    namespace.remove = (
        (removal_func, binpkg) for binpkg in
        ifilter(namespace.filters.run, (pkg.path for pkg in pkgs)))


tmp = subparsers.add_parser(
    'tmp', parents=(shared_opts,),
    description='remove tmpdir entries')
tmp_opts = tmp.add_argument_group('tmpfile options')
tmp_opts.add_argument(
    '-a', '--all', dest='wipeall', action='store_true',
    help='wipe the entire tmpdir',
    docs="""
        Force the entire tmpdir to be wiped. Note that this overrides any
        restrictions that have been specified.
    """)
@tmp.bind_final_check
def _tmp_validate_args(parser, namespace):
    tmpdir = namespace.domain.tmpdir
    dirs = ()
    files = ()

    if namespace.restrict and not namespace.wipeall:
        # create a fake repo from tmpdir entries and pull matches from it
        pkg_map = {}
        for pkg_build_dir in glob.glob(pjoin(tmpdir, '*', '*')):
            try:
                pkg = atom.atom('=' + pkg_build_dir[len(tmpdir):].lstrip(os.path.sep))
            except atom.MalformedAtom:
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
    # TODO: parallelize this
    for func, target in options.remove:
        if options.pretend:
            out.write('Would remove %s' % target)
        elif options.verbose:
            out.write('Removing %s' % target)
        try:
            if not options.pretend:
                func(target)
        except OSError as e:
            if options.verbose or not options.quiet:
                err.write("%s: failed to remove '%s': %s" % (options.prog, target, e.strerror))
            ret = 1
            continue
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
