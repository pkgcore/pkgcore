# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("pkgsets", "histo_data", "eapi_usage", "license_usage",
    "mirror_usage", "eclass_usage", "mirror_usage"
)

from pkgcore.util import commandline
from pkgcore.ebuild import portageq
import os
from snakeoil.demandload import demandload

demandload(globals(),
    'snakeoil.lists:iflatten_instance,unstable_unique',
    'snakeoil.mappings:defaultdict',
    'pkgcore:fetch',
    'pkgcore.restrictions:packages',
    'itertools:groupby,islice',
    'operator:attrgetter,itemgetter'
)

shared = (commandline.mk_argparser(domain=False, add_help=False),)
argparse_parser = commandline.mk_argparser(suppress=True, parents=shared)
subparsers = argparse_parser.add_subparsers(description="report applets")

pkgsets = subparsers.add_parser("pkgsets", help="pkgset related introspection")
mux = pkgsets.add_mutually_exclusive_group()
mux.add_argument("--all", action='store_true', default=False,
    help="display info on all pkgsets")
mux.add_argument("pkgsets", nargs="*", metavar="pkgset", default=[],
    action=commandline.StoreConfigObject, config_type='pkgset', store_name=True,
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

    missing = False
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
        data = sorted(data.iteritems(), key=itemgetter(0))
    else:
        data = sorted(data.iteritems(), key=itemgetter(1), reverse=True)

    if first:
        data = islice(data, 0, first)
    elif last:
        data = list(data)[-last:]

    for key, val in data:
        out.write(format % {'key':str(key), 'val':val,
            'percent':"%2.2f%%" % (val/total,)})


class histo_data(commandline.ArgparseCommand):

    per_repo_summary = None
    allow_no_detail = False

    def bind_to_parser(self, parser):
        mux = parser.add_mutually_exclusive_group()
        mux.add_argument("--no-final-summary", action='store_true', default=False,
            help="disable outputting a summary of data across all repos")

        parser.set_defaults(repo_summary=bool(self.per_repo_summary))
        if self.per_repo_summary:
            mux.add_argument("--no-repo-summary", dest='repo_summary',
                action='store_false',
                help="disable outputting repo summaries")

        parser.set_defaults(no_detail=False)
        if self.allow_no_detail:
            mux.add_argument("--no-detail", action='store_true', default=False,
                help="disable outputting a detail view of all repos")

        parser.add_argument("--sort-by-name", action='store_true', default=False,
            help="sort output by name, rather then by frequency")

        mux = parser.add_mutually_exclusive_group()

        mux.add_argument("--first", action="store", type=int, default=0,
            help="show only the first N detail items")

        mux.add_argument("--last", action="store", type=int, default=0,
            help="show only the last N detail items")

        parser.add_argument("repos", metavar='repo', nargs='*',
            action=commandline.StoreConfigObject, config_type='repo', store_name=True,
            default=commandline.CONFIG_ALL_DEFAULT,
            help="repositories to inspect")

        commandline.ArgparseCommand.bind_to_parser(self, parser)

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
                    print_simple_histogram(detail_data,
                        out, self.per_repo_format, repo_total,
                        sort_by_key=opts.sort_by_name,
                        first=opts.first, last=opts.last)
                out.first_prefix.pop()
            for key, val in detail_data.iteritems():
                global_stats.setdefault(key, 0)
                global_stats[key] += val
            total_pkgs += repo_total

            if not opts.repo_summary:
                continue
            out.write(out.bold, 'summary', out.reset, ': ',
                self.per_repo_summary %
                self.transform_data_to_summary(data))

        if position > 1 and not opts.no_final_summary:
            out.write()
            out.write(out.bold, 'summary', out.reset, ':')
            out.first_prefix.append('  ')
            print_simple_histogram(global_stats, out, self.summary_format,
                total_pkgs, sort_by_key=opts.sort_by_name)
            out.first_prefix.pop()
        return 0


class eapi_usage_kls(histo_data):

    per_repo_format = ("eapi: %(key)r %(val)s pkgs found, %(percent)s of the "
        "repository")

    summary_format = ("eapi: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    def get_data(self, repo, options):
        eapis = {}
        pos = 0
        for pos, pkg in enumerate(repo):
            eapis.setdefault(pkg.eapi, 0)
            eapis[pkg.eapi] += 1
        return eapis, pos + 1

eapi_usage = subparsers.add_parser("eapi_usage",
    help="report of eapi usage for targeted repositories")
eapi_usage.bind_class(eapi_usage_kls())


class license_usage_kls(histo_data):

    per_repo_format = ("license: %(key)r %(val)s pkgs found, %(percent)s of the "
        "repository")

    summary_format = ("license: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    def get_data(self, repo, options):
        data = {}
        pos = 0
        for pos, pkg in enumerate(repo):
            for license in unstable_unique(iflatten_instance(pkg.license)):
                data.setdefault(license, 0)
                data[license] += 1
        return data, pos + 1

license_usage = subparsers.add_parser("license_usage",
    help="report of license usage for targeted repositories")
license_usage.bind_class(license_usage_kls())


class eclass_usage_kls(histo_data):

    per_repo_format = ("eclass: %(key)r %(val)s pkgs found, %(percent)s of the "
        "repository")

    summary_format = ("eclass: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    def get_data(self, repo, options):
        pos, data = 0, {}
        for pos, pkg in enumerate(repo):
            for eclass in getattr(pkg, 'data', {}).get("_eclasses_", {}).keys():
                data.setdefault(eclass, 0)
                data[eclass] += 1
        return data, pos + 1

eclass_usage = subparsers.add_parser("eclass_usage",
    help="report of eclass usage for targeted repositories")
eclass_usage.bind_class(eclass_usage_kls())


class mirror_usage_kls(histo_data):

    per_repo_format = ("mirror: %(key)r %(val)s pkgs found, %(percent)s of the "
        "repository")

    summary_format = ("mirror: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    def get_data(self, repo, options):
        data = {}
        for pos, pkg in enumerate(repo):
            for fetchable in iflatten_instance(pkg.fetchables,
                fetch.fetchable):
                for mirror in fetchable.uri.visit_mirrors(
                    treat_default_as_mirror=False):
                    if isinstance(mirror, tuple):
                        mirror = mirror[0]
                    data.setdefault(mirror.mirror_name, 0)
                    data[mirror.mirror_name] += 1
        return data, pos + 1

mirror_usage = subparsers.add_parser("mirror_usage",
    help="report of SRC_URI mirror usage for targeted repositories")
mirror_usage.bind_class(mirror_usage_kls())


class distfiles_usage_kls(histo_data):

    per_repo_format = ("package: %(key)r %(val)s bytes, referencing %(percent)s of the "
        "unique total")

    per_repo_summary = ("unique total %(total)i bytes, sharing %(shared)i bytes")

    summary_format = ("package: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    allow_no_detail = True

    def bind_to_parser(self, parser):
        histo_data.bind_to_parser(self, parser)
        parser.add_argument("--include-nonmirrored", action='store_true', default=False,
            help="if set, nonmirrored  distfiles will be included in the total")
        parser.add_argument("--include-restricted", action='store_true', default=False,
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

        data = defaultdict(lambda:0)
        for filename, keys in owners.iteritems():
            for key in keys:
                data[key] += items[filename]
        unique = sum(items.itervalues())
        shared = sum(items[k] for (k,v) in owners.iteritems() if len(v) > 1)
        return (data, {"total":unique, "shared":shared}), unique

    def transform_data_to_detail(self, data):
        return data[0]

    def transform_data_to_summary(self, data):
        return data[1]


distfiles_usage = subparsers.add_parser("distfiles_usage",
    help="report detailing distfiles space usage for targeted repositories")
distfiles_usage.bind_class(distfiles_usage_kls())


#commandline_commands['portageq'] = portageq.commandline_commands
