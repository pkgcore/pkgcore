# Copyright: 2009-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("pkgsets_data", "histo_data", "eapi_usage_data", "license_usage_data",
    "mirror_usage_data", "eclass_usage_data", "mirror_usage_data"
)

from pkgcore.util.commandline import OptionParser
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

commandline_commands = {}

class pkgsets_data(OptionParser):

    #enable_domain_options = True
    description = 'inspect pkgsets available in configuration'
    usage = ('%prog pkgsets [sets-to-examine] ; if no sets specified, '
        'list the known sets')

    def _check_values(self, values, args):
        values.pkgsets = tuple(args)
        return values, ()

    def run(self, opts, out, err):
        if not opts.pkgsets:
            out.write(out.bold, 'available pkgset: ', out.reset,
                ', '.join(repr(x) for x in
                   sorted(opts.config.pkgset.iterkeys())))
            return 0
        missing = False
        for position, set_name in enumerate(opts.pkgsets):
            pkgset = opts.get_pkgset(None, set_name)
            if pkgset is None:
                missing = True
                if position:
                    out.write()
                out.write(out.bold, 'pkgset ', repr(set_name), out.reset,
                    "isn't defined, skipping.")
            else:
                if position:
                    out.write()
                out.write(out.bold, 'pkgset ', repr(set_name), out.reset, ':')
                out.first_prefix.append('  ')
                for restrict in sorted(pkgset):
                    out.write(restrict)
                out.first_prefix.pop()
        if not missing:
            return 0
        return 1

commandline_commands['pkgset'] = pkgsets_data


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


class histo_data(OptionParser):

    per_repo_summary = None
    allow_no_detail = False

    def _register_options(self):
        self.add_option("--no-final-summary", action='store_true', default=False,
            help="disable outputting a summary of data across all repos")

        if self.per_repo_summary:
            self.add_option("--no-repo-summary", action='store_true', default=False,
                help="disable outputting repo summaries")

        if self.allow_no_detail:
            self.add_option("--no-detail", action='store_true', default=False,
                help="disable outputting a detail view of all repos")

        self.add_option("--sort-by-name", action='store_true', default=False,
            help="sort output by name, rather then by frequency")

        self.add_option("--first", action="store", type='int', default=0,
            help="show only the first N detail items")

        self.add_option("--last", action="store", type='int', default=0,
            help="show only the last N detail items")

    def _check_values(self, opts, args):
        repo_conf = opts.config.repo
        if args:
            opts.repos = []
            for repo_name in args:
                if not repo_name in repo_conf:
                    self.error("no repository named %r" % (repo_name,))
                opts.repos.append((repo_name, repo_conf[repo_name]))
        else:
            opts.repos = sorted(repo_conf.items(), key=lambda x:x[0])

        if not self.allow_no_detail:
            opts.no_detail = False

        if not self.per_repo_summary:
            opts.repo_summary = False

        if opts.no_detail and opts.no_repo_summary and opts.no_final_summary:
            s = '--no-final-summary '
            if self.allow_no_detail:
                s += 'and --no-detail '
            if self.per_repo_summary:
                s += 'and --no-repo-summary '
            self.error("%s cannot be used together; pick just one" % (s,))

        if opts.last and opts.first:
            self.error("--first and --last cannot be used together; use just one")

        return opts, ()

    def get_data(self, repo, options):
        raise NotImplementedError()

    def transform_data_to_detail(self, data):
        return data

    def transform_data_to_summary(self, data):
        return data

    def run(self, opts, out, err):
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

            if opts.no_repo_summary:
                continue
            out.write(out.bold, 'summary', out.reset, ': ',
                self.per_repo_summary %
                self.transform_data_to_summary(data))

        if position > 1 and not opts.no_final_summary:
            out.write(out.bold, 'summary', out.reset, ':')
            out.first_prefix.append('  ')
            print_simple_histogram(global_stats, out, self.summary_format,
                total_pkgs, sort_by_key=opts.sort_by_name)
            out.first_prefix.pop()
        return 0


class eapi_usage_data(histo_data):

    #enable_domain_options = True
    description = 'get a breakdown of eapi usage for target repositories'
    usage = ('%prog eapi_usage [repositories to look at] ; if no repositories '
        'specified the default is to scan all')

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

commandline_commands['eapi_usage'] = eapi_usage_data


class license_usage_data(histo_data):

    description = 'get a breakdown of license usage for target repositories'
    usage = ('%prog license_usage [repositories to look at] ; if no repositories '
        'specified the default is to scan all')

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

commandline_commands['license_usage'] = license_usage_data


class eclass_usage_data(histo_data):

    description = 'get a breakdown of eclass usage for target repositories'
    usage = ('%prog eclass_usage [repositories to look at] ; if no '
        'repositories are specified it defaults to scanning all')

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

commandline_commands['eclass_usage'] = eclass_usage_data


class mirror_usage_data(histo_data):

    description = 'get a breakdown of mirror usage for target repositories'
    usage = ('%prog mirror_usage [repositories to look at] ; if no '
        'repositories are specified it defaults to scanning all')

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

commandline_commands['mirror_usage'] = mirror_usage_data

class distfiles_usage_data(histo_data):

    description = 'get a breakdown of total distfiles for target repositories'
    usage = ('%prog mirror_usage [repositories to look at] ; if no '
        'repositories are specified it defaults to scanning all')

    per_repo_format = ("package: %(key)r %(val)s bytes, referencing %(percent)s of the "
        "unique total")

    per_repo_summary = ("unique total %(total)i bytes, sharing %(shared)i bytes")

    summary_format = ("package: %(key)r %(val)s pkgs found, %(percent)s of all "
        "repositories")

    allow_no_detail = True

    def _register_options(self):
        histo_data._register_options(self)
        self.add_option("--include-nonmirrored", action='store_true', default=False,
            help="if set, nonmirrored  distfiles will be included in the total")
        self.add_option("--include-restricted", action='store_true', default=False,
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

commandline_commands['distfiles_usage'] = distfiles_usage_data
