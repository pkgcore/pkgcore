"""repository inspection interface

pinspect is used to extract various information from repos. For example,
it can perform aggregated EAPI, license, eclass, and mirror usage queries
across specified repos. Any repo type can be queried, e.g. ebuild,
binary, or vdb.

It also provides an interface to all profile specific metadata, e.g. package
masks, inheritance trees, etc. This makes it easier to inspect profile
differences without sorting through the inheritance tree and reading the raw
files.

Finally, a portageq compatible interface is provided for several commands that
were historically used in ebuilds.
"""

__all__ = (
    "pkgsets", "histo_data", "eapi_usage", "license_usage",
    "mirror_usage", "eclass_usage", "mirror_usage",
    "portageq", "query",
)

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby, islice
from operator import attrgetter, itemgetter

from snakeoil.cli import arghparse
from snakeoil.sequences import iflatten_instance, unstable_unique

from .. import fetch
from ..ebuild import inspect_profile
from ..ebuild import portageq as _portageq
from ..package import errors
from ..restrictions import packages
from ..util import commandline

pkgcore_opts = commandline.ArgumentParser(domain=False, script=(__file__, __name__))
argparser = commandline.ArgumentParser(
    suppress=True, description=__doc__, parents=(pkgcore_opts,))
subparsers = argparser.add_subparsers(description="report applets")

pkgsets = subparsers.add_parser(
    "pkgsets", description="pkgset related introspection")
mux = pkgsets.add_mutually_exclusive_group()
mux.add_argument(
    "--all", action='store_true', default=False,
    help="display info on all pkgsets")
mux.add_argument(
    "pkgsets", nargs="*", metavar="pkgset", default=[],
    action=commandline.StoreConfigObject,
    config_type='pkgset', store_name=True,
    help="pkgset to inspect")
del mux
@pkgsets.bind_main_func
def pkgsets_run(opts, out, err):
    if not opts.pkgsets:
        if not opts.all:
            out.write(out.bold, 'available pkgset(s): ', out.reset,
                      ', '.join(repr(x) for x in sorted(opts.config.pkgset)))
            return 0
        else:
            opts.pkgsets = sorted(opts.config.pkgset)

    for position, (set_name, pkgset) in enumerate(opts.pkgsets):
        if position:
            out.write()
        out.write(out.bold, 'pkgset ', repr(set_name), out.reset, ':')
        out.first_prefix.append('  ')
        for restrict in sorted(pkgset):
            out.write(restrict)
        out.first_prefix.pop()
    return 0


def print_simple_histogram(data, out, format, total, sort_by_key=False,
                           first=None, last=None):
    # do the division up front...
    total = float(total) / 100

    if sort_by_key:
        data = sorted(data.items(), key=itemgetter(0))
    else:
        data = sorted(data.items(), key=itemgetter(1), reverse=True)

    if first:
        data = islice(data, 0, first)
    elif last:
        data = list(data)[-last:]

    for key, val in data:
        out.write(format %
                  {'key': str(key), 'val': val,
                   'percent': "%2.2f%%" % (val/total,)})


class histo_data(arghparse.ArgparseCommand):

    per_repo_summary = None
    allow_no_detail = False

    def bind_to_parser(self, parser):
        mux = parser.add_mutually_exclusive_group()
        mux.add_argument(
            "--no-final-summary", action='store_true', default=False,
            help="disable outputting a summary of data across all repos")

        parser.set_defaults(repo_summary=bool(self.per_repo_summary))
        if self.per_repo_summary:
            mux.add_argument(
                "--no-repo-summary", dest='repo_summary',
                action='store_false',
                help="disable outputting repo summaries")

        parser.set_defaults(no_detail=False)
        if self.allow_no_detail:
            mux.add_argument(
                "--no-detail", action='store_true', default=False,
                help="disable outputting a detail view of all repos")

        parser.add_argument(
            "--sort-by-name", action='store_true', default=False,
            help="sort output by name, rather then by frequency")

        mux = parser.add_mutually_exclusive_group()

        mux.add_argument(
            "--first", action="store", type=int, default=0,
            help="show only the first N detail items")

        mux.add_argument(
            "--last", action="store", type=int, default=0,
            help="show only the last N detail items")

        parser.add_argument(
            "repos", metavar='repo', nargs='*',
            action=commandline.StoreRepoObject, store_name=True,
            default=commandline.CONFIG_ALL_DEFAULT,
            help="repo(s) to inspect")

        arghparse.ArgparseCommand.bind_to_parser(self, parser)

    def get_data(self, repo, options):
        raise NotImplementedError()

    def transform_data_to_detail(self, data):
        return data

    def transform_data_to_summary(self, data):
        return data

    def __call__(self, opts, out, err):
        global_stats = {}
        position = 0
        total_pkgs = 0
        for repo_name, repo in opts.repos:
            if position:
                out.write()
            position += 1
            out.write(out.bold, "repository", out.reset, ' ',
                      repr(repo_name), ':')
            data, repo_total = self.get_data(repo, opts)
            detail_data = self.transform_data_to_detail(data)
            if not opts.no_detail:
                out.first_prefix.append("  ")
                if not data:
                    out.write("no pkgs found")
                else:
                    print_simple_histogram(
                        detail_data, out, self.per_repo_format,
                        repo_total, sort_by_key=opts.sort_by_name,
                        first=opts.first, last=opts.last)
                out.first_prefix.pop()
            for key, val in detail_data.items():
                global_stats.setdefault(key, 0)
                global_stats[key] += val
            total_pkgs += repo_total

            if not opts.repo_summary:
                continue
            out.write(
                out.bold, 'summary', out.reset, ': ',
                self.per_repo_summary %
                self.transform_data_to_summary(data))

        if position > 1 and not opts.no_final_summary:
            out.write()
            out.write(out.bold, 'summary', out.reset, ':')
            out.first_prefix.append('  ')
            print_simple_histogram(
                global_stats, out, self.summary_format,
                total_pkgs, sort_by_key=opts.sort_by_name)
            out.first_prefix.pop()
        return 0


class eapi_usage_kls(histo_data):

    per_repo_format = ("eapi: %(key)r %(val)s pkgs found, %(percent)s of the repo")

    summary_format = ("eapi: %(key)r %(val)s pkgs found, %(percent)s of all repos")

    def get_data(self, repo, options):
        eapis = {}
        pos = 0
        for pos, pkg in enumerate(repo):
            eapis.setdefault(str(pkg.eapi), 0)
            eapis[str(pkg.eapi)] += 1
        return eapis, pos + 1

eapi_usage = subparsers.add_parser(
    "eapi_usage", description="report of eapi usage for targeted repos")
eapi_usage.bind_class(eapi_usage_kls())


class license_usage_kls(histo_data):

    per_repo_format = "license: %(key)r %(val)s pkgs found, %(percent)s of the repo"

    summary_format = "license: %(key)r %(val)s pkgs found, %(percent)s of all repos"

    def get_data(self, repo, options):
        data = {}
        pos = 0
        for pos, pkg in enumerate(repo):
            for license in unstable_unique(iflatten_instance(pkg.license)):
                data.setdefault(license, 0)
                data[license] += 1
        return data, pos + 1

license_usage = subparsers.add_parser(
    "license_usage", description="report of license usage for targeted repos")
license_usage.bind_class(license_usage_kls())


class eclass_usage_kls(histo_data):

    per_repo_format = "eclass: %(key)r %(val)s pkgs found, %(percent)s of the repo"

    summary_format = "eclass: %(key)r %(val)s pkgs found, %(percent)s of all repos"

    def get_data(self, repo, options):
        pos, data = 0, defaultdict(lambda:0)
        for pos, pkg in enumerate(repo):
            for eclass in getattr(pkg, 'inherited', ()):
                data[eclass] += 1
        return data, pos + 1

eclass_usage = subparsers.add_parser(
    "eclass_usage", description="report of eclass usage for targeted repos")
eclass_usage.bind_class(eclass_usage_kls())


class mirror_usage_kls(histo_data):

    per_repo_format = "mirror: %(key)r %(val)s pkgs found, %(percent)s of the repo"

    summary_format = "mirror: %(key)r %(val)s pkgs found, %(percent)s of all repos"

    def get_data(self, repo, options):
        data = {}
        for pos, pkg in enumerate(repo):
            for fetchable in iflatten_instance(pkg.fetchables, fetch.fetchable):
                for mirror in fetchable.uri.visit_mirrors(treat_default_as_mirror=False):
                    if isinstance(mirror, tuple):
                        mirror = mirror[0]
                    data.setdefault(mirror.mirror_name, 0)
                    data[mirror.mirror_name] += 1
        return data, pos + 1

mirror_usage = subparsers.add_parser(
    "mirror_usage", description="report of SRC_URI mirror usage for targeted repos")
mirror_usage.bind_class(mirror_usage_kls())


class distfiles_usage_kls(histo_data):

    per_repo_format = "package: %(key)r %(val)s bytes, referencing %(percent)s of the unique total"

    per_repo_summary = "unique total %(total)i bytes, sharing %(shared)i bytes"

    summary_format = "package: %(key)r %(val)s pkgs found, %(percent)s of all repos"

    allow_no_detail = True

    def bind_to_parser(self, parser):
        histo_data.bind_to_parser(self, parser)
        parser.add_argument(
            "--include-nonmirrored", action='store_true', default=False,
            help="if set, nonmirrored  distfiles will be included in the total")
        parser.add_argument(
            "--include-restricted", action='store_true', default=False,
            help="if set, fetch restricted distfiles will be included in the total")

    def get_data(self, repo, options):
        owners = defaultdict(set)
        iterable = repo.itermatch(packages.AlwaysTrue, sorter=sorted)
        items = {}
        for key, subiter in groupby(iterable, attrgetter("key")):
            for pkg in subiter:
                if not options.include_restricted and 'fetch' in pkg.restrict:
                    continue
                if not options.include_nonmirrored and 'mirror' in pkg.restrict:
                    continue
                for fetchable in iflatten_instance(pkg.fetchables, fetch.fetchable):
                    owners[fetchable.filename].add(key)
                    items[fetchable.filename] = fetchable.chksums.get("size", 0)

        data = defaultdict(lambda: 0)
        for filename, keys in owners.items():
            for key in keys:
                data[key] += items[filename]
        unique = sum(items.values())
        shared = sum(items[k] for (k, v) in owners.items() if len(v) > 1)
        return (data, {"total": unique, "shared": shared}), unique

    def transform_data_to_detail(self, data):
        return data[0]

    def transform_data_to_summary(self, data):
        return data[1]


distfiles_usage = subparsers.add_parser(
    "distfiles_usage",
    description="report detailing distfiles space usage for targeted repos")
distfiles_usage.bind_class(distfiles_usage_kls())

query = subparsers.add_parser(
    "query",
    description="auxiliary access to ebuild/repo info via portageq akin api")
_portageq.bind_parser(query, name='query')

portageq = subparsers.add_parser(
    "portageq", description="portageq compatible interface to query commands")
_portageq.bind_parser(portageq, compat=True)

profile = subparsers.add_parser(
    "profile", description="profile related querying")
# TODO: restrict to ebuild repos
profile_opts = profile.add_argument_group('subcommand options')
profile_opts.add_argument(
    '-r', '--repo', metavar='REPO', help='target repo',
    action=commandline.StoreRepoObject, repo_type='config')
inspect_profile.bind_parser(profile, 'profile')


def _bad_digest(pkg):
    """Check if a given package has a broken or missing digest."""
    try:
        pkg.fetchables
    except errors.MetadataException:
        return pkg, True
    return pkg, False


digests = subparsers.add_parser(
    "digests", domain=True, description="identify what packages are missing digest info")
digests.add_argument(
    'repos', nargs='*', help="repo to inspect",
    action=commandline.StoreRepoObject, allow_external_repos=True, store_name=True)
@digests.bind_main_func
def digest_manifest(options, out, err):
    for name, repo in options.repos:
        count = 0
        broken = []
        out.write(f"inspecting {name!r} repo:")
        out.flush()

        # TODO: move to ProcessPoolExecutor once underlying pkg wrapper classes can be pickled
        with ThreadPoolExecutor() as executor:
            for pkg, bad in executor.map(_bad_digest, iter(repo)):
                count += 1
                if bad:
                    broken.append(pkg)

        if count:
            if broken:
                out.write('Packages with broken digests:')
                out.first_prefix.append("  ")
                out.later_prefix.append("  ")
                for pkg in sorted(broken):
                    out.write(pkg.cpvstr)
                out.first_prefix.pop()
                out.later_prefix.pop()
                percent = len(broken) / count * 100
                out.write(
                    f"{len(broken)} out of {count} ({round(percent, 2)}%) packages "
                    "in the repo have bad checksum data"
                )
            else:
                out.write('repo has no broken digests')
        else:
            out.write("repo has no packages")

        out.write()
