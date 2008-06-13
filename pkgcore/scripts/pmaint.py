# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>: GPL/BSD2
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""
repository maintainence
"""

__all__ = ('CopyParser', 'DigestParser', 'RegenParser', 'SyncParser')

from pkgcore.util.commandline import convert_to_restrict, OptionParser
from snakeoil.demandload import demandload
demandload(globals(),
    'errno',
    'threading:Event',
    'threading:Thread',
    'Queue',
    'time:time,sleep',
    'snakeoil.osutils:pjoin',
    'pkgcore.repository:multiplex',
    'pkgcore.package:mutated',
    'pkgcore.fs:contents,livefs',
    'pkgcore.ebuild:atom,errors,digest',
    'pkgcore.restrictions.boolean:OrRestriction',
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


class SyncParser(OptionParser):

    def __init__(self, **kwargs):
        OptionParser.__init__(self, description=
            "update a local repository to match its parent",
            usage='pmaint sync [--force] [repo(s)]',
            **kwargs)
        self.add_option("--force", action='store_true', default=False,
            help="force an action")

    def check_values(self, values, args):
        values, args = OptionParser.check_values(
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
    """Update a local repositories to match their remote parent"""
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


class CopyParser(OptionParser):

    def __init__(self, **kwargs):
        OptionParser.__init__(self, description=
            "copy built pkg(s) into a repository",
            usage="pmaint copy -s source_repo -t target_repo [options] "
                "<atoms>",
            **kwargs)
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
            self.error("target repo %r is frozen; --force is required to "
                "override this" % target_repo)

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
            restrict = OrRestriction(*convert_to_restrict(args))
            for package in values.source_repo.itermatch(restrict):
                if not values.target_repo.match(package.versioned_atom):
                    values.candidates.append(package.versioned_atom)
        else:
            values.candidates = convert_to_restrict(args)

        return values, []


def copy_main(options, out, err):
    """Copy pkgs between repositories."""

    trg_repo = options.target_repo
    src_repo = options.source_repo

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
                            failures = True
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


class RegenParser(OptionParser):

    def __init__(self, **kwargs):
        OptionParser.__init__(
            self, description=__doc__, usage='%prog [options] repo [threads]',
            **kwargs)

    def check_values(self, values, args):
        values, args = OptionParser.check_values(
            self, values, args)
        if not args:
            self.error('Need a repository name.')
        if len(args) > 2:
            self.error('I do not know what to do with more than 2 arguments')

        if len(args) == 2:
            try:
                values.thread_count = int(args[1])
            except ValueError:
                self.error('%r should be an integer' % (args[1],))
            if values.thread_count <= 0:
                self.error('thread count needs to be at least 1')
        else:
            values.thread_count = 1

        try:
            values.repo = values.config.repo[args[0]]
        except KeyError:
            self.error('repo %r was not found! known repos: %s' % (
                    args[0], ', '.join(str(x) for x in values.config.repo)))

        return values, ()


def regen_iter(iterable, err):
    for x in iterable:
        try:
            x.keywords
        except RuntimeError:
            raise
        except Exception, e:
            err.write("caught exception %s for %s" % (e, x))

def reclaim_threads(threads, err):
    for x in threads:
        try:
            x.join()
        except RuntimeError:
            raise
        except Exception, e:
            err.write("caught exception %s reclaiming thread" % (e,))

def regen_main(options, out, err):
    """Regenerate a repository cache."""
    start_time = time()
    # HACK: store this here so we can assign to it from inside def passthru.
    options.count = 0
    if options.thread_count == 1:
        def passthru(iterable):
            for x in iterable:
                options.count += 1
                yield x
        regen_iter(passthru(options.repo), err)
    else:
        queue = Queue.Queue(options.thread_count * 2)
        kill = Event()
        kill.clear()
        def iter_queue(kill, qlist, timeout=0.25):
            while not kill.isSet():
                try:
                    yield qlist.get(timeout=timeout)
                except Queue.Empty:
                    continue
        regen_threads = [
            Thread(
                target=regen_iter, args=(iter_queue(kill, queue), err))
            for x in xrange(options.thread_count)]
        out.write('starting %d threads' % (options.thread_count,))
        try:
            for x in regen_threads:
                x.start()
            out.write('started')
            # now we feed the queue.
            for pkg in options.repo:
                options.count += 1
                queue.put(pkg)
        except Exception:
            kill.set()
            reclaim_threads(regen_threads, err)
            raise

        # by now, queue is fed. reliable for our uses since the queue
        # is only subtracted from.
        while not queue.empty():
            sleep(.5)
        kill.set()
        reclaim_threads(regen_threads, err)
        assert queue.empty()
    out.write("finished %d nodes in in %.2f seconds" % (options.count,
        time() - start_time))
    return 0

commandline_commands['regen'] = (RegenParser, regen_main)


class DigestParser(OptionParser):

    def __init__(self, **kwargs):
        OptionParser.__init__(
            self, description="generate digests for given atoms", **kwargs)
        self.add_option('-t', '--type', type='choice',
            choices=("manifest1", "manifest2", "both"), default="both",
            help="type of manifest to generate (defaults to both). "
            "valid values are: 'manifest1', 'manifest2', 'both'")

    def check_values(self, values, args):
        values, args = OptionParser.check_values(
            self, values, args)

        if not args:
            self.error('Specify a repo')
        repo = args.pop(0)
        try:
            values.repo = values.config.repo[repo]
        except KeyError:
            self.error("repo %r was not found, known repos-\n%s" %
                (repo, format_seq(values.config.repo.keys())))

        if values.type == "both":
            values.type = ("manifest1", "manifest2")
        else:
            values.type = (values.type,)

        if not args:
            self.error('Specify an atom')
        values.atoms = []
        for arg in args:
            try:
                values.atoms.append(atom.atom(arg))
            except errors.MalformedAtom, e:
                self.error(str(e))

        return values, ()


def digest_main(options, out, err):
    """Write Manifests and digests"""

    for atom in options.atoms:
        pkgs = options.repo.match(atom)
        if not pkgs:
            err.write('No matches for %s\n' % (options.atom,))
            return 1
        for pkg in pkgs:
            if "manifest1" in options.type:
                if options.debug:
                    out.write('Writing digest for %s:' % pkg.cpvstr)
                location = pjoin(pkg.repo.location, pkg.key, "files",
                      "digest-%s-%s" % (pkg.versioned_atom.package,
                                        pkg.versioned_atom.fullver))
                digest.serialize_digest(open(location, 'w'), pkg.fetchables)
            if "manifest2" in options.type:
                if options.debug:
                    out.write('Writing Manifest for %s:' % pkg.cpvstr)
                digest.serialize_manifest("%s/%s" %(pkg.repo.location, pkg.key),
                    pkg.fetchables)

# XXX: harring disabled this for 0.3.
# re-enable it when the bits update manifest.
#commandline_commands['digest'] = (DigestParser, digest_main)
