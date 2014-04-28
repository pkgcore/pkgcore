# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>: GPL/BSD2
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
repository maintainence
"""

__all__ = ("sync", "sync_main", "copy", "copy_main", "regen", "regen_main",
    "perl_rebuild", "perl_rebuild_main", "env_update", "env_update_main")

from pkgcore.util import commandline
from snakeoil.demandload import demandload
demandload(globals(),
    'os',
    'errno',
    'time',
    'snakeoil.osutils:pjoin,listdir_dirs',
    'pkgcore:spawn',
    'pkgcore.operations:observer',
    'pkgcore.repository:multiplex',
    'pkgcore.package:mutated',
    'pkgcore.fs:contents,livefs',
    'pkgcore.ebuild:processor,triggers',
    'pkgcore.merge:triggers@merge_triggers',
    'pkgcore.sync:base@sync_base',
    're',
)

def format_seq(seq, formatter=repr):
    if not seq:
        seq = None
    elif len(seq) == 1:
        seq = seq[0]
    else:
        seq = tuple(sorted(str(x) for x in seq))
    return formatter(seq)


shared_options = (commandline.mk_argparser(domain=False, add_help=False),)
argparser = commandline.mk_argparser(suppress=True, parents=shared_options,
    description="commandline access to various system/repository maintenance functionality")
subparsers = argparser.add_subparsers(description="general system maintenance")

sync = subparsers.add_parser("sync", parents=shared_options,
    description="synchronize a local repository with it's defined remote")
sync.add_argument('repos', nargs='*', help="repositories to sync",
    action=commandline.StoreRepoObject, store_name=True, raw=True)
@sync.bind_main_func
def sync_main(options, out, err):
    """Update a local repositories to match their remote parent"""
    succeeded, failed = [], []
    seen = set()
    for name, repo in options.repos:
        # rewrite the name if it has the usual prefix
        if name.startswith("raw:"):
            name = name[len("raw:"):]
        repo_id = getattr(repo, 'repo_id', None)
        if repo in seen or repo_id in seen:
            out.write("*** skipping %r, already synced" % name)
            continue

        if repo_id:
            seen.add(repo_id)
        seen.add(repo)
        ops = repo.operations
        if not ops.supports("sync"):
            continue
        out.write("*** syncing %r..." % name)
        try:
            ret = ops.sync()
        except sync_base.syncer_exception as se:
            out.write("*** failed syncing %r- caught exception %r" % (name, se))
            failed.append(name)
            continue
        if not ret:
            out.write("*** failed syncing %r" % name)
            failed.append(name)
        else:
            succeeded.append(name)
            out.write("*** synced %r" % name)
    total = len(succeeded) + len(failed)
    if total > 1:
        if succeeded:
            out.write("*** synced %s" % format_seq(sorted(succeeded)))
        if failed:
            err.write("!!! failed sync'ing %s" % format_seq(sorted(failed)))
    if failed:
        return 1
    return 0


copy = subparsers.add_parser("copy", parents=shared_options,
    description="copy binpkgs between repositories; primarily useful for "
    "quickpkging a livefs pkg")
copy.add_argument('target_repo', action=commandline.StoreRepoObject,
    writable=True, help="repository to add packages to")
copy.add_argument('-s', '--source-repo', default=None,
    action=commandline.StoreRepoObject,
    help="copy strictly from the supplied repository; else it copies from "
    "wherever a match is found")
commandline.make_query(copy, nargs='+', dest='query',
    help="packages matching any of these restrictions will be selected "
    "for copying")
copy.add_argument('-i', '--ignore-existing', default=False, action='store_true',
    help="if a matching pkg already exists in the target, don't update it")

@copy.bind_main_func
def copy_main(options, out, err):
    """Copy pkgs between repositories."""

    src_repo = options.source_repo
    if src_repo is None:
        src_repo = multiplex.tree(*options.config.repo.values())
    trg_repo = options.target_repo
    src_repo = options.source_repo

    failures = False

    for pkg in src_repo.itermatch(options.query):
        if options.ignore_existing and trg_repo.has_match(pkg.versioned_atom):
            out.write("skipping %s; it exists already." % (pkg,))
            continue

        out.write("copying %s... " % (pkg,))
        if getattr(getattr(pkg, 'repo', None), 'livefs', False):
            out.write("forcing regen of contents due to src being livefs..")
            new_contents = contents.contentsSet(mutable=True)
            for fsobj in pkg.contents:
                try:
                    new_contents.add(livefs.gen_obj(fsobj.location))
                except OSError as oe:
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
            pkg = mutated.MutatedPkg(pkg, {'contents':new_contents})

        trg_repo.operations.install_or_replace(pkg).finish()

        out.write("completed\n")
    if failures:
        return 1
    return 0

def _get_default_jobs(namespace, attr):
    # we intentionally overschedule for SMP; the main python thread
    # isn't too busy, thus we want to keep all bash workers going.
    val = spawn.get_proc_count()
    if val > 1:
        val += 1
    setattr(namespace, attr, val)

regen = subparsers.add_parser("regen", parents=shared_options,
    description="regenerate repository caches")
regen.add_argument("--disable-eclass-caching", action='store_true',
    default=False,
    help="For regen operation, pkgcore internally turns on an "
    "optimization that caches eclasses into individual functions "
    "thus parsing the eclass only twice max per EBD processor.  Disabling "
    "this optimization via this option results in ~2x slower "
    "regeneration. Disable it only if you suspect the optimization "
    "is somehow causing issues.")
regen.add_argument("-t", "--threads", type=int,
    default=commandline.DelayedValue(_get_default_jobs, 100),
    help="number of threads to use for regeneration.  Defaults to using all "
    "available processors")
regen.add_argument("--force", action='store_true', default=False,
    help="force regeneration to occur regardless of staleness checks")
regen.add_argument("repo", action=commandline.StoreRepoObject,
    help="repository to regenerate caches for")
@regen.bind_main_func
def regen_main(options, out, err):
    """Regenerate a repository cache."""

    repo = options.repo
    if not repo.operations.supports("regen_cache"):
        out.write("repository %s doesn't support cache regeneration" % (options.repo,))
        return 0

    start_time = time.time()
    repo.operations.regen_cache(threads=options.threads,
        observer=observer.formatter_output(out), force=options.force,
            eclass_caching=(not options.disable_eclass_caching))
    end_time = time.time()
    out.write("finished %d nodes in in %.2f seconds" % (len(options.repo),
        end_time - start_time))
    return 0


perl_rebuild = subparsers.add_parser("perl-rebuild",
    parents=(commandline.mk_argparser(add_help=False),),
    description="EXPERIMENTAL: perl-rebuild support for use after upgrading perl")
perl_rebuild.add_argument("new_version",
    help="the new perl version; 5.12.3 for example")
@perl_rebuild.bind_main_func
def perl_rebuild_main(options, out, err):

    path = pjoin(options.domain.root, "usr/lib/perl5",
        options.new_version)
    if not os.path.exists(path):
        err.write("version %s doesn't seem to be installed; can't find it at %r" %
            (options.new_version, path))
        return 1

    base = pjoin(options.domain.root, "/usr/lib/perl5")
    potential_perl_versions = [x.replace(".", "\.") for x in listdir_dirs(base)
        if x.startswith("5.") and x != options.new_version]

    if len(potential_perl_versions) == 1:
        subpattern = potential_perl_versions[0]
    else:
        subpattern = "(?:%s)" % ("|".join(potential_perl_versions),)
    matcher = re.compile("/usr/lib(?:64|32)?/perl5/(?:%s|vendor_perl/%s)" %
        (subpattern, subpattern)).match

    for pkg in options.domain.all_livefs_repos:
        contents = getattr(pkg, 'contents', ())
        if not contents:
            continue
        # scan just directories...
        for fsobj in contents.iterdirs():
            if matcher(fsobj.location):
                out.write("%s" % (pkg.unversioned_atom,))
                break
    return 0


env_update = subparsers.add_parser("env-update", description="update env.d and ldconfig",
    parents=(commandline.mk_argparser(add_help=False),))
env_update.add_argument("--skip-ldconfig", action='store_true', default=False,
    help="do not update etc/ldso.conf and ld.so.cache")
@env_update.bind_main_func
def env_update_main(options, out, err):
    root = getattr(options.domain, 'root', None)
    if root is None:
        err.write("domain specified lacks a root seting; is it a virtual or rmeote domain?")
        return 1

    out.write("updating env for %r..." % (root,))
    triggers.perform_env_update(root,
        skip_ldso_update=options.skip_ldconfig)
    if not options.skip_ldconfig:
        out.write("update ldso cache/elf hints for %r..." % (root,))
        merge_triggers.update_elf_hints(root)
    return 0


mirror = subparsers.add_parser("mirror",
    description="mirror the sources for a package in full- grab everything"
    " that could be required",
    parents=(commandline.mk_argparser(add_help=False),))
mirror.add_argument("-f", "--ignore-failures", action='store_true',
    default=False,
    help="if a failure occurs, keep going.  If this option isn't given, it'll"
    " stop at the first failure encountered")
commandline.make_query(mirror, nargs='+', dest='query',
    help="query of which packages to mirror")
@mirror.bind_main_func
def mirror_main(options, out, err):
    domain = options.domain
    warnings = False
    for pkg in domain.all_repos.itermatch(options.query):
        pkg_ops = domain.pkg_operations(pkg)
        if not pkg_ops.supports("mirror"):
            warnings = True
            out.write("pkg %s doesn't support mirroring\n" % (pkg,))
            continue
        out.write("mirroring %s" % (pkg,))
        if not pkg_ops.mirror():
            out.error("pkg %s failed to mirror" % (pkg,))
            if not options.ignore_failures:
                return 2
            out.info("ignoring..\n")
            continue
    if warnings:
        return 1
    return 0


digest = subparsers.add_parser("digest",
    description="update a repositories package manifest/digest information",
    parents=(commandline.mk_argparser(add_help=False),))
digest.add_argument("--repo", "--repository", help="repository to update",
    action=commandline.StoreRepoObject)
commandline.make_query(digest, nargs='+', dest='query',
    help="packages matching any of these restrictions will have their"
    " manifest/digest updated")
@digest.bind_main_func
def digest_main(options, out, err):
    domain = options.domain
    repo = options.repo
    if options.repo is None:
       repo = domain.all_repos
    repo_ops = repo.operations
    obs=observer.formatter_output(out)
    if not repo_ops.supports("digests"):
        out.write("no repository support for digests\n")
        return 1
    elif not repo.has_match(options.query):
        out.write("query %s doesn't match anything\n" % (options.query,))
        return 1
    if not repo_ops.digests(domain, options.query, observer=obs):
        out.write("some errors were encountered...")
        return 1
    return 0
