# Copyright: 2009-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.util.commandline import OptionParser
import os
from snakeoil.demandload import demandload

demandload(globals(),
    'snakeoil.lists:iflatten_instance,unstable_unique',
    'pkgcore:fetch',
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


def print_simple_histogram(data, out, format, total, sort_by_key=False):
    # do the division up front...

    total = float(total) / 100

    if sort_by_key:
        data = sorted(data.iteritems(), key=lambda x:x[0])
    else:
        data = sorted(data.iteritems(), key=lambda x:x[1], reverse=True)

    for key, val in data:
        out.write(format % {'key':str(key), 'val':val,
            'percent':"%2.2f%%" % (val/total,)})


class histo_data(OptionParser):

    def _register_options(self):
        self.add_option("--no-summary", action='store_true', default=False,
            help="disable outputting a summary of all repos")
        self.add_option("--sort-by-name", action='store_true', default=False,
            help="sort output by name, rather then by frequency")

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
        return opts, ()

    def get_data(self, repo):
        raise NotImplementedError()

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
            data, repo_total = self.get_data(repo)
            out.first_prefix.append("  ")
            if not data:
                out.write("no pkgs found")
            else:
                print_simple_histogram(data, out, self.per_repo_format,
                    repo_total, sort_by_key=opts.sort_by_name)
            out.first_prefix.pop()
            for key, val in data.iteritems():
                global_stats.setdefault(key, 0)
                global_stats[key] += val
            total_pkgs += repo_total

        if position > 1 and not opts.no_summary:
            out.write()
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

    def get_data(self, repo):
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

    def get_data(self, repo):
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

    def get_data(self, repo):
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

    def get_data(self, repo):
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
