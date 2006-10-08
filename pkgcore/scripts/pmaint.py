# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository maintainence
"""

from pkgcore.util import commandline

class OptionParser(commandline.OptionParser):

    def __init__(self):
        commandline.OptionParser.__init__(self, description=__doc__)
        self.add_option("--sync", action='store_true', default=False,
            help="sync repositories")
        self.add_option("-r", "--repo", action='append',
            help="specify a specific repo to work on; defaults to all "
                "applicable otherwise")
        self.add_option("--force", action='store_true', default=False,
            help="force an action")


def do_sync(config, repos, out, err, force):
    failed = []
    for x in repos:
        out.write("*** syncing %r..." % x)
        r = config.repo[x]
        if not r.syncable:
            out.write("*** %r is non syncable, continuing" % x)
            continue
        if not r.sync():
            failed.append(r, force=force)
            out.write("*** failed syncing %s" % x)
            failed.append(x)
        else:
            out.write("*** synced %s" % x)
    return failed

def main(config, options, out, err):
    if not options.sync:
        err.write("need at least one directive; --sync is the only supported "
            "command currently (see --help)\n")
        return 1

    repos = options.repo
    if not repos:
        repos = config.repo.keys()
    failed = do_sync(config, repos, out, err, options.force)
    if failed:
        err.write("!!! synced: %r\n!!! failed syncing: %r\n" % 
            (sorted(set(repos).differenced(failed)),
            sorted(failed)))
        return 1
    return 0
