"""system/repository maintenance utility"""

import argparse
import os
import textwrap
import time
from multiprocessing import cpu_count
from os.path import join as pjoin
from unittest.mock import patch

from snakeoil.cli import arghparse
from snakeoil.fileutils import AtomicWriteFile
from snakeoil.sequences import unique_stable

from .. import landlock
from ..cache.flat_hash import md5_cache
from ..config import load_config
from ..ebuild import overlays, portage_conf, triggers
from ..ebuild import repository as ebuild_repo
from ..ebuild.cpv import CPV
from ..ebuild.eclass import EclassDoc
from ..exceptions import PkgcoreUserException
from ..fs import contents, livefs
from ..merge import triggers as merge_triggers
from ..operations import OperationError
from ..operations import observer as observer_mod
from ..package import mutated
from ..package.errors import MetadataException
from ..repository.util import get_raw_repos
from ..util import commandline

pkgcore_opts = commandline.ArgumentParser(domain=False, script=(__file__, __name__))
argparser = commandline.ArgumentParser(
    suppress=True, description=__doc__, parents=(pkgcore_opts,)
)
subparsers = argparser.add_subparsers(description="general system maintenance")

shared_options = (
    commandline.ArgumentParser(
        config=False,
        color=False,
        debug=False,
        quiet=False,
        verbose=False,
        version=False,
        domain=False,
        add_help=False,
    ),
)
shared_options_domain = (
    commandline.ArgumentParser(
        config=False,
        color=False,
        debug=False,
        quiet=False,
        verbose=False,
        version=False,
        domain=True,
        add_help=False,
    ),
)

sync = subparsers.add_parser(
    "sync",
    parents=shared_options,
    description="synchronize a local repository with its defined remote",
)


class _StoreSyncRepos(commandline.StoreRepoObject):
    """Store the repos to sync, defaulting to every configured one.

    An import already names what to sync, so it turns that default off.
    """

    def _real_call(self, parser, namespace, values, option_string=None):
        if not values and (namespace.import_repos or namespace.masters_of):
            setattr(namespace, self.dest, [])
            return
        super()._real_call(parser, namespace, values, option_string)


sync.add_argument(
    "repos",
    metavar="repo",
    nargs="*",
    help="repo(s) to sync",
    action=_StoreSyncRepos,
    store_name=True,
    repo_type="config",
)
sync.add_argument(
    "-f",
    "--force",
    action="store_true",
    default=False,
    help="force syncing to occur regardless of staleness checks",
)
sync.add_argument(
    "--import",
    dest="import_repos",
    metavar="REPO",
    action="append",
    default=[],
    help="add a repo from Gentoo's repository list, then sync it",
    docs="""
        Look a repository up by name in Gentoo's published repository list,
        write a ``repos.conf`` entry for it, and sync it. Pass the option
        again to add more than one repo.

        New repos land beside the repos already being synced, which is
        ``/var/db/repos`` on an ordinary install, and get a file of their own
        when ``repos.conf`` is a directory. The list is fetched from
        https://api.gentoo.org/overlays/repositories.xml and cached locally.

        A repo that's already configured is simply synced, so an import can be
        repeated without failing.

        Importing leaves the rest of the configured repos alone; name them as
        arguments to sync those as well.
    """,
)
sync.add_argument(
    "--import-masters",
    dest="masters_of",
    metavar="PATH",
    type=arghparse.existent_dir,
    help="add and sync the repos a given repo inherits from",
    docs="""
        Read the masters of the repo at the given path, add the ones that
        aren't configured yet, and sync them all.

        Masters of masters are followed as each repo is synced and its own
        ``layout.conf`` becomes readable, so the repo ends up with everything
        it inherits from present and current. That makes it the one command a
        CI run needs before checking a repo it doesn't own the parents of.
    """,
)


def _sync_repo(options, out, err, repo_name, sync_func) -> bool:
    """Run one sync, reporting how it went."""
    out.write(f"*** syncing {repo_name}")
    ret = False
    err_msg = ""
    # repo operations don't yet take an observer, thus flush
    # output to keep lines consistent.
    out.flush()
    err.flush()
    try:
        ret = sync_func(force=options.force, verbosity=options.verbosity)
    except OperationError as e:
        exc = getattr(e, "__cause__", e)
        if not isinstance(exc, PkgcoreUserException):
            raise
        err_msg = f": {exc}"
    except PkgcoreUserException as e:
        # syncers reached directly raise on their own behalf
        err_msg = f": {e}"
    if ret:
        out.write(f"*** synced {repo_name}")
    else:
        out.write(f"!!! failed syncing {repo_name}{err_msg}")
    return bool(ret)


def _import_repos(options, out, err):
    """Add the requested repos to repos.conf and sync them.

    Returns:
        list: names of the repos synced
        list: names of the repos that couldn't be imported or synced
    """
    config_dir = options.config_path or portage_conf.find_config_dir()
    if not os.path.isdir(config_dir):
        raise PkgcoreUserException(f"not a portage config dir: {config_dir!r}")
    conf_path = pjoin(config_dir, "repos.conf")

    pending = list(options.import_repos)
    if follow_masters := options.masters_of is not None:
        if not os.path.isdir(pjoin(options.masters_of, "profiles")):
            raise PkgcoreUserException(f"not an ebuild repo: {options.masters_of!r}")
        pending.extend(overlays.repo_masters(options.masters_of))

    # only worth fetching once something actually has to be looked up
    available = None
    succeeded, failed, seen = [], [], set()

    while pending:
        configured = overlays.configured_repos(conf_path)
        wave = []
        for repo_name in unique_stable(pending):
            if repo_name in seen:
                continue
            seen.add(repo_name)
            if repo_name in configured:
                # nothing to add, but it was asked for, so sync it like any other
                wave.append(repo_name)
                continue
            if available is None:
                available = overlays.remote_repos()
            if (repo := available.get(repo_name)) is None:
                out.write(f"!!! {repo_name} isn't in the repository list")
                failed.append(repo_name)
            elif not repo.sources:
                out.write(f"!!! {repo_name} has no source pkgcore can sync from")
                failed.append(repo_name)
            else:
                sync_type, sync_uri = repo.sources[0]
                dest = overlays.add_repos_conf_entry(
                    conf_path,
                    repo_name,
                    pjoin(overlays.repos_base(configured), repo_name),
                    sync_type,
                    sync_uri,
                )
                out.write(f"*** added {repo_name} to {dest}")
                wave.append(repo_name)

        pending = []
        if not wave:
            break
        # the new repos only reach the config once it's been reparsed
        config = load_config(location=options.config_path, debug=options.debug)
        configured = overlays.configured_repos(conf_path)
        for repo_name in wave:
            syncer = config.objects.syncer[f"sync:{repo_name}"]
            if not _sync_repo(options, out, err, repo_name, syncer.sync):
                failed.append(repo_name)
                continue
            succeeded.append(repo_name)
            if follow_masters:
                # now that it's synced, its own masters can be read
                pending.extend(overlays.repo_masters(configured[repo_name]["location"]))
    return succeeded, failed


@sync.bind_main_func
def sync_main(options, out, err):
    """Update local repos to match their remotes."""
    succeeded, failed = [], []

    if options.import_repos or options.masters_of is not None:
        succeeded, failed = _import_repos(options, out, err)

    for repo_name, repo in unique_stable(options.repos):
        # rewrite the name if it has the usual prefix
        repo_name = repo_name.removeprefix("conf:")

        if not repo.operations.supports("sync"):
            continue
        elif repo_name in succeeded or repo_name in failed:
            # an import already dealt with this one
            continue
        if _sync_repo(options, out, err, repo_name, repo.operations.sync):
            succeeded.append(repo_name)
        else:
            failed.append(repo_name)

    out.flush()
    err.flush()
    total = len(succeeded) + len(failed)
    if total > 1:
        results = []
        succeeded = ", ".join(sorted(succeeded))
        failed = ", ".join(sorted(failed))
        if succeeded:
            results.append(f"*** synced: {succeeded}")
        if failed:
            results.append(f"!!! failed: {failed}")
        results = "\n".join(results)
        out.write(f"\n*** sync results:\n{results}")
    return 1 if failed else 0


# TODO: restrict to required repo types
copy = subparsers.add_parser(
    "copy",
    parents=shared_options_domain,
    description="copy binpkgs between repos; primarily useful for "
    "quickpkging a livefs pkg",
)
copy.add_argument(
    "target_repo",
    action=commandline.StoreRepoObject,
    repo_type="binary-raw",
    writable=True,
    help="repository to add packages to",
)
commandline.make_query(
    copy,
    nargs="+",
    dest="query",
    help="packages matching any of these restrictions will be selected for copying",
)
copy_opts = copy.add_argument_group("subcommand options")
copy_opts.add_argument(
    "-s",
    "--source-repo",
    default=None,
    repo_type="installed",
    action=commandline.StoreRepoObject,
    help="copy strictly from the supplied repository; else it copies from "
    "wherever a match is found",
)
copy_opts.add_argument(
    "-i",
    "--ignore-existing",
    default=False,
    action="store_true",
    help="if a matching pkg already exists in the target, don't update it",
)
landlock.add_sandbox_arg(copy_opts, "copying")


def _copy_writable_paths(source_repo, target_repo):
    """Everything copying pkgs into *target_repo* legitimately writes."""
    yield target_repo.location
    yield from landlock.writable_cache_paths(*get_raw_repos(source_repo))


@copy.bind_main_func
def copy_main(options, out, err):
    """Copy pkgs between repos."""
    source_repo = options.source_repo
    if source_repo is None:
        source_repo = options.domain.all_source_repos
    target_repo = options.target_repo

    landlock.confine_from(options, *_copy_writable_paths(source_repo, target_repo))

    failures = False

    for pkg in source_repo.itermatch(options.query):
        if options.ignore_existing and pkg.versioned_atom in target_repo:
            out.write(f"skipping existing pkg: {pkg.cpvstr}")
            continue
        # TODO: remove this once we limit src repos to non-virtual (pkg.provided) repos
        if not getattr(pkg, "package_is_real", True):
            out.write(f"skipping virtual pkg: {pkg.cpvstr}")
            continue

        out.write(f"copying {pkg}... ")
        if getattr(getattr(pkg, "repo", None), "livefs", False):
            out.write("forcing regen of contents due to src being livefs..")
            new_contents = contents.contentsSet(mutable=True)
            for fsobj in pkg.contents:
                try:
                    new_contents.add(livefs.gen_obj(fsobj.location))
                except FileNotFoundError:
                    err.write(
                        f"warning: dropping fs obj {fsobj!r} since it doesn't exist"
                    )
                except OSError as oe:
                    err.write(
                        f"failed accessing fs obj {fsobj!r}; {oe}\naborting this copy"
                    )
                    failures = True
                    new_contents = None
                    break
            if new_contents is None:
                continue
            pkg = mutated.MutatedPkg(pkg, {"contents": new_contents})

        target_repo.operations.install_or_replace(pkg).finish()
        out.write("completed\n")

    if failures:
        return 1
    return 0


def _get_default_jobs(namespace, attr):
    # we intentionally overschedule for SMP; the main python thread
    # isn't too busy, thus we want to keep all bash workers going.
    val = cpu_count()
    if val > 1:
        val += 1
    setattr(namespace, attr, val)


def _write_error(e: OSError, target: str) -> str:
    """Describe a failed write, naming the path it actually failed on.

    Updates go through :py:class:`AtomicWriteFile`, so a failure usually
    concerns its temporary file rather than the file being updated.
    """
    if e.filename and e.filename != target:
        return f"{e.strerror}: {e.filename!r}"
    return e.strerror


def update_use_local_desc(repo, observer):
    """Update a repo's local USE flag description cache (profiles/use.local.desc)"""
    ret = 0
    use_local_desc = pjoin(repo.location, "profiles", "use.local.desc")
    f = None

    def _raise_xml_error(exc):
        observer.error(f"{cat}/{pkg}: failed parsing metadata.xml: {exc!s}")
        nonlocal ret
        ret = 1

    try:
        f = AtomicWriteFile(use_local_desc)
        f.write(
            textwrap.dedent(
                """\
            # This file is deprecated as per GLEP 56 in favor of metadata.xml.
            # Please add your descriptions to your package's metadata.xml ONLY.
            # * generated automatically using pmaint *\n\n"""
            )
        )
        with patch("pkgcore.log.logger.error", _raise_xml_error):
            for cat, pkgs in sorted(repo.packages.items()):
                for pkg in sorted(pkgs):
                    metadata = repo._get_metadata_xml(cat, pkg)
                    for flag, desc in sorted(metadata.local_use.items()):
                        f.write(f"{cat}/{pkg}:{flag} - {desc}\n")
        f.close()
    except OSError as e:
        observer.error(
            f"Unable to update use.local.desc file {use_local_desc!r}: {_write_error(e, use_local_desc)}"
        )
        ret = os.EX_IOERR
    finally:
        if f is not None:
            f.discard()

    return ret


def update_pkg_desc_index(repo, observer):
    """Update a repo's package description cache (metadata/pkg_desc_index)"""
    ret = 0
    pkg_desc_index = pjoin(repo.location, "metadata", "pkg_desc_index")
    f = None
    try:
        f = AtomicWriteFile(pkg_desc_index)
        for cat, pkgs in sorted(repo.packages.items()):
            for pkg in sorted(pkgs):
                cpvs = sorted(CPV(cat, pkg, v) for v in repo.versions[(cat, pkg)])
                # get the most recent pkg description, skipping bad pkgs
                for cpv in reversed(cpvs):
                    try:
                        desc = repo[(cat, pkg, cpv.fullver)].description
                        versions = " ".join(x.fullver for x in cpvs)
                        f.write(f"{cat}/{pkg} {versions}: {desc}\n")
                        break
                    except MetadataException:
                        # should be caught and outputted already by cache regen
                        ret = 1
        f.close()
    except OSError as e:
        observer.error(
            f"Unable to update pkg_desc_index file {pkg_desc_index!r}: {_write_error(e, pkg_desc_index)}"
        )
        ret = os.EX_IOERR
    finally:
        if f is not None:
            f.discard()

    return ret


regen = subparsers.add_parser(
    "regen", parents=shared_options_domain, description="regenerate repository caches"
)
regen.add_argument(
    "repos",
    metavar="repo",
    nargs="*",
    action=commandline.StoreRepoObject,
    repo_type="source-raw",
    allow_external_repos=True,
    help="repo(s) to regenerate caches for",
)
regen_opts = regen.add_argument_group("subcommand options")
regen_opts.add_argument(
    "--disable-eclass-caching",
    action="store_true",
    default=False,
    help="""
        For regen operation, pkgcore internally turns on an optimization that
        caches eclasses into individual functions thus parsing the eclass only
        twice max per EBD processor. Disabling this optimization via this
        option results in ~2x slower regeneration. Disable it only if you
        suspect the optimization is somehow causing issues.
    """,
)
regen_opts.add_argument(
    "-t",
    "--threads",
    type=int,
    default=arghparse.DelayedValue(_get_default_jobs, 100),
    help="number of threads to use",
    docs="""
        Number of threads to use for regeneration, defaults to using all
        available processors.
    """,
)
regen_opts.add_argument(
    "--force",
    action="store_true",
    default=False,
    help="force regeneration to occur regardless of staleness checks or repo settings",
)
regen_opts.add_argument(
    "--dir",
    dest="cache_dir",
    type=arghparse.create_dir,
    help="use separate directory to store repository caches",
)
landlock.add_sandbox_arg(regen_opts, "regenerating")
regen_opts.add_argument(
    "--rsync",
    action="store_true",
    default=False,
    help="perform actions necessary for rsync repos (update metadata/timestamp.chk)",
)
regen_opts.add_argument(
    "--use-local-desc",
    action="store_true",
    default=False,
    help="update local USE flag description cache (profiles/use.local.desc)",
)
regen_opts.add_argument(
    "--pkg-desc-index",
    action="store_true",
    default=False,
    help="update package description cache (metadata/pkg_desc_index)",
)


def _regen_writable_paths(options):
    """Everything a regen of the selected repos legitimately writes."""
    for repo in unique_stable(options.repos):
        if options.cache_dir is not None:
            # the per-repo subdirectory is created on demand
            yield options.cache_dir
        else:
            yield from landlock.writable_cache_paths(repo)
        if options.rsync or options.pkg_desc_index:
            yield pjoin(repo.location, "metadata")
        if options.use_local_desc:
            yield pjoin(repo.location, "profiles")


@regen.bind_main_func
def regen_main(options, out, err):
    """Regenerate a repository cache."""
    landlock.confine_from(options, *_regen_writable_paths(options))

    ret = []

    observer = observer_mod.formatter_output(out)
    for repo in unique_stable(options.repos):
        if options.cache_dir is not None:
            # recreate new repo object with cache dir override
            cache = (md5_cache(pjoin(options.cache_dir.rstrip(os.sep), repo.repo_id)),)
            repo = ebuild_repo.tree(options.config, repo.config, cache=cache)
        if not repo.operations.supports("regen_cache"):
            out.write(f"repo {repo} doesn't support cache regeneration")
            continue
        elif not getattr(repo, "cache", False) and not options.force:
            out.write(f"skipping repo {repo}: cache disabled")
            continue

        start_time = time.time()
        ret.append(
            repo.operations.regen_cache(
                threads=options.threads,
                observer=observer,
                force=options.force,
                eclass_caching=(not options.disable_eclass_caching),
            )
        )
        end_time = time.time()

        if options.verbosity > 0:
            out.write(
                f"finished {len(repo)} nodes in {end_time - start_time:.2f} seconds"
            )

        if options.rsync:
            timestamp = pjoin(repo.location, "metadata", "timestamp.chk")
            try:
                with open(timestamp, "w") as f:
                    f.write(time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime()))
            except OSError as e:
                err.write(
                    f"Unable to update timestamp file {timestamp!r}: {e.strerror}"
                )
                ret.append(os.EX_IOERR)

        if options.use_local_desc:
            ret.append(update_use_local_desc(repo, observer))
        if options.pkg_desc_index:
            ret.append(update_pkg_desc_index(repo, observer))

    return int(any(ret))


env_update = subparsers.add_parser(
    "env-update", description="update env.d and ldconfig", parents=shared_options_domain
)
env_update_opts = env_update.add_argument_group("subcommand options")
env_update_opts.add_argument(
    "--skip-ldconfig",
    action="store_true",
    default=False,
    help="do not update etc/ldso.conf and ld.so.cache",
)


@env_update.bind_main_func
def env_update_main(options, out, err):
    root = getattr(options.domain, "root", None)
    if root is None:
        env_update.error(
            "domain specified lacks a root setting; is it a virtual or remote domain?"
        )

    out.write(f"updating env for {root!r}...")
    try:
        triggers.perform_env_update(root, skip_ldso_update=options.skip_ldconfig)
    except PermissionError:
        env_update.error("failed updating env, lacking permissions")
    if not options.skip_ldconfig:
        out.write(f"update ldso cache/elf hints for {root!r}...")
        merge_triggers.update_elf_hints(root)
    return 0


class EclassArgs(argparse.Action):
    """Determine eclass arguments for `pmaint eclass`."""

    def __call__(self, parser, namespace, values, option_string=None):
        if values:
            eclasses = []
            for val in values:
                path = os.path.realpath(val)
                if os.path.isdir(path):
                    eclasses.extend(os.listdir(path))
                elif val.endswith(".eclass"):
                    eclasses.append(path)
                else:
                    raise argparse.ArgumentError(self, f"invalid eclass: {val!r}")
            eclasses = sorted(x for x in eclasses if x.endswith(".eclass"))
        else:
            eclass_dir = pjoin(namespace.repo.location, "eclass")
            try:
                files = sorted(os.listdir(eclass_dir))
            except FileNotFoundError:
                files = []
            eclasses = [pjoin(eclass_dir, x) for x in files if x.endswith(".eclass")]
            if not eclasses:
                parser.error(f"{namespace.repo.repo_id} repo: no eclasses found")

        setattr(namespace, self.dest, eclasses)


eclass = subparsers.add_parser(
    "eclass", parents=shared_options_domain, description="generate eclass docs"
)
eclass.add_argument(
    "eclasses",
    nargs="*",
    help="eclasses to target",
    action=arghparse.Delayed,
    target=EclassArgs,
    priority=1001,
)
eclass_opts = eclass.add_argument_group("subcommand options")
eclass_opts.add_argument(
    "--dir", dest="output_dir", type=arghparse.create_dir, help="output directory"
)
landlock.add_sandbox_arg(eclass_opts, "generating eclass docs")
eclass_opts.add_argument(
    "-o",
    "--output",
    dest="output_format",
    default="{eclass}.eclass.{format}",
    help="output file name format",
    docs="""
        Output file name format. Defaults to ``{eclass}.eclass.{format}``. You
        can use ``{eclass}`` and ``{format}`` placeholders to customize the
        output file name. The filename can have path separator, for example:
        ``{eclass}/{eclass}.eclass.{format}``.
    """,
)
eclass_opts.add_argument(
    "-f",
    "--format",
    help="output format",
    default="man",
    choices=("rst", "man", "html", "devbook"),
)
eclass_opts.add_argument(
    "-r",
    "--repo",
    help="target repository",
    action=commandline.StoreRepoObject,
    repo_type="ebuild-raw",
    allow_external_repos=True,
    docs="""
        Target repository to search for eclasses. If no repo is specified the default repo is used.
    """,
)


@eclass.bind_delayed_default(1000, "repo")
def _eclass_default_repo(namespace, attr):
    """Use default repo if none is selected."""
    repo = namespace.config.get_default("repo")
    setattr(namespace, attr, repo)


@eclass.bind_delayed_default(1000, "output_dir")
def _eclass_default_output_dir(namespace, attr):
    """Use CWD as output dir if unset."""
    setattr(namespace, attr, os.getcwd())


@eclass.bind_main_func
def _eclass_main(options, out, err):
    landlock.confine_from(options, options.output_dir)

    failed = []

    # determine output file extension
    ext_map = {"man": "5"}
    ext = ext_map.get(options.format, options.format)

    for path in options.eclasses:
        try:
            filename = pjoin(
                options.output_dir,
                options.output_format.format(
                    eclass=os.path.basename(path).removesuffix(".eclass"),
                    format=ext,
                ),
            )
            if options.verbosity > 0:
                out.write("Compiling: ", path)
            obj = EclassDoc(path, sourced=True)
            data = getattr(obj, f"to_{options.format}")()
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "wt") as f:
                f.write(data)
        except NotImplementedError as e:
            err.write(f"{eclass.prog}: failed {path!r}: {e}")
            raise
        except ValueError as e:
            # skip eclasses lacking eclassdoc support
            err.write(f"{eclass.prog}: skipping {path!r}: {e}")
            err.flush()
        except OSError as e:
            err.write(f"{eclass.prog}: error: {path!r}: {e}")
            err.flush()
            failed.append(path)

    return int(any(failed))
