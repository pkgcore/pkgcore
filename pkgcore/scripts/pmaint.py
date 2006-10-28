# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository maintainence
"""

from pkgcore.util import commandline

class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, description=__doc__, **kwargs)
        self.add_option("--sync", action='store_true', default=False,
            help="sync repositories")
        self.add_option("-r", "--repo", action='append',
            help="specify a specific repo to work on; defaults to all "
                "applicable otherwise")
        self.add_option("--force", action='store_true', default=False,
            help="force an action")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if not values.sync:
            self.error(
                "need at least one directive; "
                "--sync is the only supported command currently (see --help)")
        if not values.repo:
            values.repo = values.config.repo.keys()
        return values, args


def do_sync(config, repos, out, err, force):
    failed = []
    seen = set()
    for x in repos:
        r = config.repo[x]
        if r in seen:
            continue
        seen.add(r)
        if not r.syncable:
            continue
        out.write("*** syncing %r..." % x)
        if not r.sync():
            failed.append(r, force=force)
            out.write("*** failed syncing %s" % x)
            failed.append(x)
        else:
            out.write("*** synced %s" % x)
    return failed

def main(options, out, err):
    failed = do_sync(options.config, options.repo, out, err, options.force)
    if failed:
        err.write("!!! synced: %r\n!!! failed syncing: %r\n" % 
            (sorted(set(repos).differenced(failed)),
            sorted(failed)))
        return 1
    return 0
