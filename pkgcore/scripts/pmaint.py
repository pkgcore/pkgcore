# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository maintainence
"""

from pkgcore.util import commandline

commandline_commands = {}

def format_seq(seq, formatter=repr):
    if not seq:
        seq = None
    elif len(seq) == 1:
        seq = seq[0]
    return formatter(seq)

class SyncOptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, description=
            "update a local repository to match it's parent", **kwargs)
        self.add_option("-r", "--repo", action='append',
            help="specify a specific repo to work on; defaults to all "
                "applicable otherwise")
        self.add_option("--force", action='store_true', default=False,
            help="force an action")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        if not args:
            values.repo = values.config.repo.keys()
        else:
            for x in args:
                if x not in values.config.repo:
                    self.error("repo %r doesn't exist:\nvalid repos %r" % 
                        (x, values.config.repo.keys()))
            values.repo = args
        return values, args

def sync_main(options, out, err):
    """update a local repositories to match their remote parent"""
    config = options.config
    succeeded, failed = [], []
    seen = set()
    for x in options.repo:
        r = config.repo[x]
        if r in seen:
            continue
        seen.add(r)
        if not r.syncable:
            continue
        out.write("*** syncing %r..." % x)
        if not r.sync():
            failed.append(r, force=options.force)
            out.write("*** failed syncing %r" % x)
            failed.append(x)
        else:
            succeeded.append(x)
            out.write("*** synced %r" % x)
    if len(succeeded) + len(failed) > 1:
        out.write("*** synced %r\n" % format_seq(sorted(succeeded)))
        if failed:
            err.write("!!! failed sync'ing %r\n" % format_seq(sorted(failed)))
    if failed:
        return 1
    return 0

commandline_commands['sync'] = (SyncOptionParser, sync_main)


# end sync bits.

class CopyPkgParser(commandline.OptionParser):
    
    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, doc=
            "copy built pkg(s) into a repository", **kwargs)
        self.add_option("-s", "--source-repo",
            help="copy from just the specified repository; else defaults "
                "to finding any match")
        self.add_option("--force", action='store_true', default=False,
            help="try and force the copy if the target repository is marked as "
                "immutable")
        
