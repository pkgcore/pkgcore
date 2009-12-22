# Copyright: 2009-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.util.commandline import OptionParser
import os
from snakeoil.demandload import demandload

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

def collect_repo_eapi_stats(repo):
    eapis = {}
    for pkg in repo:
        eapis.setdefault(pkg.eapi, 0)
        eapis[pkg.eapi] += 1
    return eapis


class eapi_data(OptionParser):

    #enable_domain_options = True
    description = 'get a breakdown of eapi usage for target repositories'
    usage = ('%prog eapi [repositories to look at] ; if no repositories '
        'specified the default is to scan all')

    def _register_options(self):
        self.add_option("--no-summary", action='store_true', default=False,
            help="disable outputting a summary of all repos")

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

    def run(self, opts, out, err):
        global_stats = {}
        position = 0
        for repo_name, repo in opts.repos:
            if position:
                out.write()
            position += 1
            out.write(out.bold, "repository", out.reset, ' ',
                repr(repo_name), ':')
            data = collect_repo_eapi_stats(repo)
            out.first_prefix.append("  ")
            if not data:
                out.write("no pkgs found")
            else:
                # do the division up front
                total = float(sum(data.itervalues())) / 100
                for key, val in sorted(data.iteritems(), key=lambda x:x[1],
                    reverse=True):
                    out.write("eapi: ", repr(str(key)), ' ', val,
                        " pkgs found, ", ("%2.2f" % (val/total)),
                        "% of the repository")
            out.first_prefix.pop()
            for key, val in data.iteritems():
                global_stats.setdefault(key, 0)
                global_stats[key] += val

        if position > 1 and not opts.no_summary:
            out.write()
            out.write(out.bold, 'summary', out.reset, ':')
            out.first_prefix.append('  ')
            total = float(sum(global_stats.itervalues())) / 100
            for key, val in sorted(global_stats.iteritems(), key=lambda x:x[1],
                reverse=True):
                out.write("eapi: ", repr(str(key)), ' ', val,
                    " pkgs found, ", ("%2.2f" % (val/total)),
                    "% of all repositories")
            out.first_prefix.pop()
        return 0


commandline_commands['eapi'] = eapi_data
