# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository maintainence
"""

from pkgcore.util import commandline
from pkgcore.util.demandload import demandload

demandload(globals(), "pkgcore.repository:multiplex "
    "pkgcore.util:parserestrict "
    "pkgcore.package:mutated "
    "pkgcore.fs:contents,livefs "
    "pkgcore.restrictions:packages "
    "pkgcore.restrictions.boolean:OrRestriction "
    "errno "
    )

commandline_commands = {}

def format_seq(seq, formatter=repr):
    if not seq:
        seq = None
    elif len(seq) == 1:
        seq = seq[0]
    else:
        seq = tuple(sorted(str(x) for x in seq))
    return formatter(seq)


class SyncParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, description=
            "update a local repository to match it's parent", **kwargs)
        self.add_option("--force", action='store_true', default=False,
            help="force an action")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        if not args:
            values.repos = values.config.repo.keys()
        else:
            for x in args:
                if x not in values.config.repo:
                    self.error("repo %r doesn't exist:\nvalid repos %r" %
                        (x, values.config.repo.keys()))
            values.repos = args
        return values, []

def sync_main(options, out, err):
    """update a local repositories to match their remote parent"""
    config = options.config
    succeeded, failed = [], []
    seen = set()
    for x in options.repos:
        r = config.repo[x]
        if r in seen:
            continue
        seen.add(r)
        if not r.syncable:
            continue
        out.write("*** syncing %r..." % x)
        if not r.sync(force=options.force):
            out.write("*** failed syncing %r" % x)
            failed.append(x)
        else:
            succeeded.append(x)
            out.write("*** synced %r" % x)
    if len(succeeded) + len(failed) > 1:
        out.write("*** synced %s" % format_seq(sorted(succeeded)))
        if failed:
            err.write("!!! failed sync'ing %s" % format_seq(sorted(failed)))
    if failed:
        return 1
    return 0

commandline_commands['sync'] = (SyncParser, sync_main)


class CopyParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(self, description=
            "copy built pkg(s) into a repository", **kwargs)
        self.add_option("-s", "--source-repo",
            help="copy from just the specified repository; else defaults "
                "to finding any match")
        self.add_option("-t", "--target-repo", default=None,
            help="repository to copy packages into; if specified, "
                "you don't need to specify the target repo as the last arg.  "
                "Mainly useful for xargs invocations")
        self.add_option("--ignore-existing", "-i", default=False,
            action='store_true',
            help="skip existing pkgs, instead of treating it as an overwrite "
            "error")
        self.add_option("--copy-missing", action="store_true", default=False,
            help="Copy packages missing in target repo from source repo")
        self.add_option("--force", action='store_true', default=False,
            help="try and force the copy if the target repository is marked as "
                "immutable")

    def check_values(self, values, args):
        l = len(args)
        if not values.target_repo and l < 2:
            self.error("target_report wasn't specified- specify it either as "
                "the last arguement, or via --target-repo")

        if values.target_repo is not None:
            target_repo = values.target_repo
        else:
            target_repo = args.pop(-1)

        try:
            values.target_repo = values.config.repo[target_repo]
        except KeyError:
            self.error("target repo %r was not found, known repos-\n%s" %
                (target_repo, format_seq(values.config.repo.keys())))

        if values.target_repo.frozen and not values.force:
            self.error("target repo %r is frozen; --force is required to override "
                "this" % target_repo)

        if values.source_repo:
            try:
                values.source_repo = values.config.repo[values.source_repo]
            except KeyError:
                self.error("source repo %r was not found, known repos-\n%s" %
                    (values.source_repo, format_seq(values.config.repo.keys())))
        else:
            values.source_repo = multiplex.tree(*values.config.repos.values())

        values.candidates = []
        if values.copy_missing:
            restrict = OrRestriction(self.convert_to_restrict(args))
            for package in values.source_repo.itermatch(restrict):
                if not values.target_repo.match(package.versioned_atom):
                    values.candidates.append(package.versioned_atom)
        else:
            values.candidates = self.convert_to_restrict(args)

        return values, []


def copy_main(options, out, err):
    "copy pkgs between repositories"

    trg_repo = options.target_repo
    src_repo = options.source_repo

    transfers = []
    failures = False
    kwds = {'force': options.force}

    for candidate in options.candidates:
        matches = src_repo.match(candidate)
        if not matches:
            err.write("didn't find any matching pkgs for %r" % candidate)
            failures = True
            continue

        for src in matches:
            existing = trg_repo.match(src.versioned_atom)
            args = []
            pkg = src
            if len(existing) > 1:
                err.write(
                    "skipping %r; tried to replace more then one pkg %r..." %
                    (src, format_seq(existing)))
                failures = True
                continue
            elif len(existing) == 1:
                if options.ignore_existing:
                    out.write("skipping %s, since %s exists already" %
                        (src, existing[0]))
                    continue
                out.write("replacing %s with %s... " % (src, existing[0]))
                op = trg_repo.replace
                args = existing
            else:
                out.write("copying %s... " % src)
                op = trg_repo.install

            if src.repo.livefs:
                out.write("forcing regen of contents due to src being livefs..")
                new_contents = contents.contentsSet(mutable=True)
                for fsobj in src.contents:
                    try:
                        new_contents.add(livefs.gen_obj(fsobj.location))
                    except OSError, oe:
                        if oe.errno != errno.ENOENT:
                            err.write("failed accessing fs obj %r; %r\n"
                                "aborting this copy" %
                                (fsobj, oe))
                            failure = True
                            new_contents = None
                            break
                        err.write("warning: dropping fs obj %r since it "
                            "doesn't exist" % fsobj)
                if new_contents is None:
                    continue
                pkg = mutated.MutatedPkg(src, {'contents':new_contents})

            op = op(*(args + [pkg]), **kwds)
            op.finish()

            out.write("completed\n")
    if failures:
        return 1
    return 0

commandline_commands['copy'] = (CopyParser, copy_main)
