"""system/repository maintenance utility"""

__all__ = (
    "sync", "sync_main", "copy", "copy_main", "regen", "regen_main",
    "perl_rebuild", "perl_rebuild_main", "env_update", "env_update_main",
)

import argparse
import logging
import os
import re
import textwrap
import time
from multiprocessing import cpu_count

from snakeoil.cli import arghparse
from snakeoil.contexts import patch
from snakeoil.fileutils import AtomicWriteFile
from snakeoil.osutils import listdir_dirs, pjoin
from snakeoil.sequences import iter_stable_unique

from ..cache.flat_hash import md5_cache
from ..ebuild import repository as ebuild_repo
from ..ebuild import triggers
from ..ebuild.cpv import CPV
from ..ebuild.eclass import EclassDoc
from ..exceptions import PkgcoreUserException
from ..fs import contents, livefs
from ..merge import triggers as merge_triggers
from ..operations import OperationError
from ..operations import observer as observer_mod
from ..package import mutated
from ..package.errors import MetadataException
from ..restrictions import packages
from ..util import commandline
from ..util.parserestrict import parse_match

pkgcore_opts = commandline.ArgumentParser(domain=False, script=(__file__, __name__))
argparser = commandline.ArgumentParser(
    suppress=True, description=__doc__, parents=(pkgcore_opts,))
subparsers = argparser.add_subparsers(description="general system maintenance")

shared_options = (commandline.ArgumentParser(
    config=False, color=False, debug=False, quiet=False, verbose=False,
    version=False, domain=False, add_help=False),)
shared_options_domain = (commandline.ArgumentParser(
    config=False, color=False, debug=False, quiet=False, verbose=False,
    version=False, domain=True, add_help=False),)

sync = subparsers.add_parser(
    "sync", parents=shared_options,
    description="synchronize a local repository with its defined remote")
sync.add_argument(
    'repos', metavar='repo', nargs='*', help="repo(s) to sync",
    action=commandline.StoreRepoObject, store_name=True, repo_type='config')
sync.add_argument(
    '-f', '--force', action='store_true', default=False,
    help="force syncing to occur regardless of staleness checks")
@sync.bind_main_func
def sync_main(options, out, err):
    """Update local repos to match their remotes."""
    succeeded, failed = [], []

    for repo_name, repo in iter_stable_unique(options.repos):
        # rewrite the name if it has the usual prefix
        if repo_name.startswith("conf:"):
            repo_name = repo_name[5:]

        if not repo.operations.supports("sync"):
            continue
        out.write(f"*** syncing {repo_name}")
        ret = False
        err_msg = ''
        # repo operations don't yet take an observer, thus flush
        # output to keep lines consistent.
        out.flush()
        err.flush()
        try:
            ret = repo.operations.sync(
                force=options.force, verbosity=options.verbosity)
        except OperationError as e:
            exc = getattr(e, '__cause__', e)
            if not isinstance(exc, PkgcoreUserException):
                raise
            err_msg = f': {exc}'
        if not ret:
            out.write(f"!!! failed syncing {repo_name}{err_msg}")
            failed.append(repo_name)
        else:
            succeeded.append(repo_name)
            out.write(f"*** synced {repo_name}")

    out.flush()
    err.flush()
    total = len(succeeded) + len(failed)
    if total > 1:
        results = []
        succeeded = ', '.join(sorted(succeeded))
        failed = ', '.join(sorted(failed))
        if succeeded:
            results.append(f"*** synced: {succeeded}")
        if failed:
            results.append(f"!!! failed: {failed}")
        results = "\n".join(results)
        out.write(f"\n*** sync results:\n{results}")
    return 1 if failed else 0


# TODO: restrict to required repo types
copy = subparsers.add_parser(
    "copy", parents=shared_options_domain,
    description="copy binpkgs between repos; primarily useful for "
    "quickpkging a livefs pkg")
copy.add_argument(
    'target_repo', action=commandline.StoreRepoObject, repo_type='binary-raw',
    writable=True, help="repository to add packages to")
commandline.make_query(
    copy, nargs='+', dest='query',
    help="packages matching any of these restrictions will be selected "
    "for copying")
copy_opts = copy.add_argument_group("subcommand options")
copy_opts.add_argument(
    '-s', '--source-repo', default=None, repo_type='installed',
    action=commandline.StoreRepoObject,
    help="copy strictly from the supplied repository; else it copies from "
    "wherever a match is found")
copy_opts.add_argument(
    '-i', '--ignore-existing', default=False, action='store_true',
    help="if a matching pkg already exists in the target, don't update it")
@copy.bind_main_func
def copy_main(options, out, err):
    """Copy pkgs between repos."""
    source_repo = options.source_repo
    if source_repo is None:
        source_repo = options.domain.all_source_repos
    target_repo = options.target_repo

    failures = False

    for pkg in source_repo.itermatch(options.query):
        if options.ignore_existing and pkg.versioned_atom in target_repo:
            out.write(f"skipping existing pkg: {pkg.cpvstr}")
            continue
        # TODO: remove this once we limit src repos to non-virtual (pkg.provided) repos
        if not getattr(pkg, 'package_is_real', True):
            out.write(f"skipping virtual pkg: {pkg.cpvstr}")
            continue

        out.write(f"copying {pkg}... ")
        if getattr(getattr(pkg, 'repo', None), 'livefs', False):
            out.write("forcing regen of contents due to src being livefs..")
            new_contents = contents.contentsSet(mutable=True)
            for fsobj in pkg.contents:
                try:
                    new_contents.add(livefs.gen_obj(fsobj.location))
                except FileNotFoundError:
                    err.write(
                        f"warning: dropping fs obj {fsobj!r} since it doesn't exist")
                except OSError as oe:
                    err.write(
                        f"failed accessing fs obj {fsobj!r}; {oe}\n"
                        "aborting this copy")
                    failures = True
                    new_contents = None
                    break
            if new_contents is None:
                continue
            pkg = mutated.MutatedPkg(pkg, {'contents': new_contents})

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


def update_use_local_desc(repo, observer):
    """Update a repo's local USE flag description cache (profiles/use.local.desc)"""
    ret = 0
    use_local_desc = pjoin(repo.location, "profiles", "use.local.desc")
    f = None

    def _raise_xml_error(exc):
        observer.error(f'{cat}/{pkg}: failed parsing metadata.xml: {str(exc)}')
        nonlocal ret
        ret = 1

    try:
        f = AtomicWriteFile(use_local_desc)
        f.write(textwrap.dedent('''\
            # This file is deprecated as per GLEP 56 in favor of metadata.xml.
            # Please add your descriptions to your package's metadata.xml ONLY.
            # * generated automatically using pmaint *\n\n'''))
        with patch('pkgcore.log.logger.error', _raise_xml_error):
            for cat, pkgs in sorted(repo.packages.items()):
                for pkg in sorted(pkgs):
                    metadata = repo._get_metadata_xml(cat, pkg)
                    for flag, desc in sorted(metadata.local_use.items()):
                        f.write(f'{cat}/{pkg}:{flag} - {desc}\n')
        f.close()
    except IOError as e:
        observer.error(
            f"Unable to update use.local.desc file {use_local_desc!r}: {e.strerror}")
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
                        versions = ' '.join(x.fullver for x in cpvs)
                        f.write(f"{cat}/{pkg} {versions}: {desc}\n")
                        break
                    except MetadataException as e:
                        # should be caught and outputted already by cache regen
                        ret = 1
        f.close()
    except IOError as e:
        observer.error(
            f"Unable to update pkg_desc_index file {pkg_desc_index!r}: {e.strerror}")
        ret = os.EX_IOERR
    finally:
        if f is not None:
            f.discard()

    return ret


regen = subparsers.add_parser(
    "regen", parents=shared_options_domain,
    description="regenerate repository caches")
regen.add_argument(
    'repos', metavar='repo', nargs='*',
    action=commandline.StoreRepoObject, repo_type='source-raw', allow_external_repos=True,
    help="repo(s) to regenerate caches for")
regen_opts = regen.add_argument_group("subcommand options")
regen_opts.add_argument(
    "--disable-eclass-caching", action='store_true', default=False,
    help="""
        For regen operation, pkgcore internally turns on an optimization that
        caches eclasses into individual functions thus parsing the eclass only
        twice max per EBD processor. Disabling this optimization via this
        option results in ~2x slower regeneration. Disable it only if you
        suspect the optimization is somehow causing issues.
    """)
regen_opts.add_argument(
    "-t", "--threads", type=int,
    default=arghparse.DelayedValue(_get_default_jobs, 100),
    help="number of threads to use",
    docs="""
        Number of threads to use for regeneration, defaults to using all
        available processors.
    """)
regen_opts.add_argument(
    "--force", action='store_true', default=False,
    help="force regeneration to occur regardless of staleness checks or repo settings")
regen_opts.add_argument(
    "--dir", dest='cache_dir', type=arghparse.create_dir,
    help="use separate directory to store repository caches")
regen_opts.add_argument(
    "--rsync", action='store_true', default=False,
    help="perform actions necessary for rsync repos (update metadata/timestamp.chk)")
regen_opts.add_argument(
    "--use-local-desc", action='store_true', default=False,
    help="update local USE flag description cache (profiles/use.local.desc)")
regen_opts.add_argument(
    "--pkg-desc-index", action='store_true', default=False,
    help="update package description cache (metadata/pkg_desc_index)")
@regen.bind_main_func
def regen_main(options, out, err):
    """Regenerate a repository cache."""
    ret = []

    observer = observer_mod.formatter_output(out)
    for repo in iter_stable_unique(options.repos):
        if options.cache_dir is not None:
            # recreate new repo object with cache dir override
            cache = (md5_cache(pjoin(options.cache_dir.rstrip(os.sep), repo.repo_id)),)
            repo = ebuild_repo.tree(
                options.config, repo.config, cache=cache)
        if not repo.operations.supports("regen_cache"):
            out.write(f"repo {repo} doesn't support cache regeneration")
            continue
        elif not getattr(repo, 'cache', False) and not options.force:
            out.write(f"skipping repo {repo}: cache disabled")
            continue

        start_time = time.time()
        ret.append(repo.operations.regen_cache(
            threads=options.threads, observer=observer, force=options.force,
            eclass_caching=(not options.disable_eclass_caching)))
        end_time = time.time()

        if options.verbosity > 0:
            out.write(
                "finished %d nodes in %.2f seconds" %
                (len(repo), end_time - start_time))

        if options.rsync:
            timestamp = pjoin(repo.location, "metadata", "timestamp.chk")
            try:
                with open(timestamp, "w") as f:
                    f.write(time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime()))
            except IOError as e:
                err.write(f"Unable to update timestamp file {timestamp!r}: {e.strerror}")
                ret.append(os.EX_IOERR)

        if options.use_local_desc:
            ret.append(update_use_local_desc(repo, observer))
        if options.pkg_desc_index:
            ret.append(update_pkg_desc_index(repo, observer))

    return int(any(ret))


perl_rebuild = subparsers.add_parser(
    "perl-rebuild", parents=shared_options_domain,
    description="EXPERIMENTAL: perl-rebuild support for use after upgrading perl")
perl_rebuild.add_argument(
    "new_version", help="the new perl version; 5.12.3 for example")
@perl_rebuild.bind_main_func
def perl_rebuild_main(options, out, err):
    path = pjoin(options.domain.root, "usr/lib/perl5", options.new_version)
    if not os.path.exists(path):
        perl_rebuild.error(
            f"version {options.new_version} doesn't seem to be installed; "
            f"can't find it at {path!r}")

    base = pjoin(options.domain.root, "/usr/lib/perl5")
    potential_perl_versions = [
        x.replace(".", "\\.") for x in listdir_dirs(base)
        if x.startswith("5.") and x != options.new_version]

    if len(potential_perl_versions) == 1:
        subpattern = potential_perl_versions[0]
    else:
        subpattern = "(?:%s)" % ("|".join(potential_perl_versions),)
    matcher = re.compile(
        "/usr/lib(?:64|32)?/perl5/(?:%s|vendor_perl/%s)" %
        (subpattern, subpattern)).match

    for pkg in options.domain.all_installed_repos:
        contents = getattr(pkg, 'contents', ())
        if not contents:
            continue
        # scan just directories...
        for fsobj in contents.iterdirs():
            if matcher(fsobj.location):
                out.write(str(pkg.unversioned_atom))
                break
    return 0


env_update = subparsers.add_parser(
    "env-update", description="update env.d and ldconfig",
    parents=shared_options_domain)
env_update_opts = env_update.add_argument_group("subcommand options")
env_update_opts.add_argument(
    "--skip-ldconfig", action='store_true', default=False,
    help="do not update etc/ldso.conf and ld.so.cache")
@env_update.bind_main_func
def env_update_main(options, out, err):
    root = getattr(options.domain, 'root', None)
    if root is None:
        env_update.error("domain specified lacks a root setting; is it a virtual or remote domain?")

    out.write(f"updating env for {root!r}...")
    try:
        triggers.perform_env_update(root, skip_ldso_update=options.skip_ldconfig)
    except PermissionError:
        env_update.error("failed updating env, lacking permissions")
    if not options.skip_ldconfig:
        out.write(f"update ldso cache/elf hints for {root!r}...")
        merge_triggers.update_elf_hints(root)
    return 0


mirror = subparsers.add_parser(
    "mirror", parents=shared_options_domain,
    description="mirror the sources for a package in full- grab everything that could be required")
commandline.make_query(
    mirror, nargs='+', dest='query',
    help="query of which packages to mirror")
mirror_opts = mirror.add_argument_group("subcommand options")
mirror_opts.add_argument(
    "-f", "--ignore-failures", action='store_true', default=False,
    help="if a failure occurs, keep going",
    docs="""
        Keep going even if a failure occurs. By default, the first failure
        encountered stops the process.
    """)
@mirror.bind_main_func
def mirror_main(options, out, err):
    domain = options.domain
    warnings = False
    for pkg in domain.all_source_repos.itermatch(options.query):
        pkg_ops = domain.pkg_operations(pkg)
        if not pkg_ops.supports("mirror"):
            warnings = True
            out.write(f"pkg {pkg} doesn't support mirroring\n")
            continue
        out.write(f"mirroring {pkg}")
        if not pkg_ops.mirror():
            out.error(f"pkg {pkg} failed to mirror")
            if not options.ignore_failures:
                return 2
            out.info("ignoring..\n")
            continue
    if warnings:
        return 1
    return 0


digest = subparsers.add_parser(
    "digest", parents=shared_options_domain,
    description="update package manifests")
digest.add_argument(
    'target', nargs='*',
    help="packages matching any of these restrictions will have their "
         "manifest/digest updated",
    docs="""
        Packages matching any of these restrictions will have their manifest
        entries updated; however, if no target is specified one of the
        following two cases occurs:

        - If a repo is specified, the entire repo is manifested.
        - If a repo isn't specified, a path restriction is created based on the
          current working directory. In other words, if `pmaint digest` is run
          within an ebuild's directory, all the ebuilds within that directory
          will be manifested. If the current working directory isn't
          within any configured repo, all repos are manifested.
    """)
digest_opts = digest.add_argument_group("subcommand options")
digest_opts.add_argument(
    "-f", "--force", help="forcibly remanifest specified packages",
    action='store_true',
    docs="""
        Force package manifest files to be rewritten. Note that this requires
        downloading all distfiles.
    """)
digest_opts.add_argument(
    "-m", "--mirrors", help="enable fetching from Gentoo mirrors",
    action='store_true',
    docs="""
        Enable checking Gentoo mirrors first for distfiles. This is disabled by
        default because manifest generation is often performed when adding new
        ebuilds with distfiles that aren't on Gentoo mirrors yet.
    """)
digest_opts.add_argument(
    "-r", "--repo", help="target repository",
    action=commandline.StoreRepoObject, repo_type='ebuild-raw', allow_external_repos=True,
    docs="""
        Target repository to search for matches. If no repo is specified all
        ebuild repos are used.
    """)
@digest.bind_final_check
def _digest_validate(parser, namespace):
    repo = namespace.repo
    targets = namespace.target
    restrictions = []
    if repo is not None:
        if not targets:
            restrictions.append(repo.path_restrict(repo.location))
    else:
        # if we're currently in a known ebuild repo use it, otherwise use all ebuild repos
        cwd = os.getcwd()
        repo = namespace.domain.ebuild_repos_raw.repo_match(cwd)
        if repo is None:
            repo = namespace.domain.all_ebuild_repos_raw

        if not targets:
            try:
                restrictions.append(repo.path_restrict(cwd))
            except ValueError:
                # we're not in a configured repo so manifest everything
                restrictions.extend(repo.path_restrict(x.location) for x in repo.trees)

    if not repo.operations.supports("digests"):
        digest.error("no repository support for digests")

    for target in targets:
        if os.path.exists(target):
            try:
                restrictions.append(repo.path_restrict(target))
            except ValueError as e:
                digest.error(e)
        else:
            try:
                restrictions.append(parse_match(target))
            except ValueError:
                digest.error(f"invalid atom: {target!r}")

    restriction = packages.OrRestriction(*restrictions)
    namespace.restriction = restriction
    namespace.repo = repo


@digest.bind_main_func
def digest_main(options, out, err):
    repo = options.repo

    failed = repo.operations.digests(
        domain=options.domain,
        restriction=options.restriction,
        observer=observer_mod.formatter_output(out),
        mirrors=options.mirrors,
        force=options.force)

    return int(any(failed))


class EclassArgs(argparse.Action):
    """Determine eclass arguments for `pmaint eclass`."""

    def __call__(self, parser, namespace, values, option_string=None):
        if values:
            eclasses = []
            for val in values:
                path = os.path.realpath(val)
                if os.path.isdir(path):
                    eclasses.extend(os.listdir(path))
                elif val.endswith('.eclass'):
                    eclasses.append(path)
                else:
                    raise argparse.ArgumentError(self, f'invalid eclass: {val!r}')
            eclasses = sorted(x for x in eclasses if x.endswith('.eclass'))
        else:
            eclass_dir = pjoin(namespace.repo.location, 'eclass')
            try:
                files = sorted(os.listdir(eclass_dir))
            except FileNotFoundError:
                files = []
            eclasses = [pjoin(eclass_dir, x) for x in files if x.endswith('.eclass')]
            if not eclasses:
                parser.error(f'{namespace.repo.repo_id} repo: no eclasses found')

        setattr(namespace, self.dest, eclasses)


eclass = subparsers.add_parser(
    "eclass", parents=shared_options_domain,
    description="generate eclass docs")
eclass.add_argument(
    'eclasses', nargs='*', help="eclasses to target",
    action=arghparse.Delayed, target=EclassArgs, priority=1001)
eclass_opts = eclass.add_argument_group("subcommand options")
eclass_opts.add_argument(
    "--dir", dest='output_dir', type=arghparse.create_dir, help="output directory")
eclass_opts.add_argument(
    "-f", "--format", help="output format",
    default='man', choices=('rst', 'man', 'html'))
eclass_opts.add_argument(
    "-r", "--repo", help="target repository",
    action=commandline.StoreRepoObject, repo_type='ebuild-raw', allow_external_repos=True,
    docs="""
        Target repository to search for eclasses. If no repo is specified the default repo is used.
    """)


@eclass.bind_delayed_default(1000, 'repo')
def _eclass_default_repo(namespace, attr):
    """Use default repo if none is selected."""
    repo = namespace.config.get_default('repo')
    setattr(namespace, attr, repo)


@eclass.bind_delayed_default(1000, 'output_dir')
def _eclass_default_output_dir(namespace, attr):
    """Use CWD as output dir if unset."""
    setattr(namespace, attr, os.getcwd())


@eclass.bind_main_func
def _eclass_main(options, out, err):
    # suppress all eclassdoc parsing warnings
    logging.getLogger('pkgcore').setLevel(100)
    failed = []

    # determine output file extension
    ext_map = {'man': '5'}
    ext = ext_map.get(options.format, options.format)

    for path in options.eclasses:
        try:
            with open(pjoin(options.output_dir, f'{os.path.basename(path)}.{ext}'), 'wt') as f:
                obj = EclassDoc(path)
                convert_func = getattr(obj, f'to_{options.format}')
                f.write(convert_func())
        except ValueError as e:
            # skip eclasses lacking eclassdoc support
            err.write(f'{eclass.prog}: skipping {path!r}: {e}')
            err.flush()
        except IOError as e:
            err.write(f'{eclass.prog}: error: {path!r}: {e}')
            err.flush()
            failed.append(path)

    return int(any(failed))
