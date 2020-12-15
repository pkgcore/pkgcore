"""low-level ebuild utility"""

import sys

from snakeoil.cli.exceptions import ExitException
from snakeoil.strings import pluralism

from ..operations import OperationError, observer
from ..package.errors import MetadataException
from ..util.commandline import ArgumentParser, StoreTarget

argparser = ArgumentParser(description=__doc__, script=(__file__, __name__))
argparser.add_argument(
    'target', action=StoreTarget,
    allow_ebuild_paths=True, allow_external_repos=True,
    help="atom or ebuild matching a pkg to execute phases from")
argparser.add_argument('phase', nargs='+', help="phases to run")
phase_opts = argparser.add_argument_group("phase options")
phase_opts.add_argument(
    "--no-auto", action='store_true', default=False,
    help="run just the specified phases; "
         "it's up to the invoker to get the order right")


@argparser.bind_final_check
def _validate_args(parser, namespace):
    namespace.repo = namespace.domain.ebuild_repos_unfiltered


@argparser.bind_main_func
def main(options, out, err):
    token, restriction = options.target[0]
    domain = options.domain

    try:
        pkgs = options.repo.match(restriction, pkg_filter=None)
    except MetadataException as e:
        error = e.msg(verbosity=options.verbosity)
        argparser.error(f'{e.pkg.cpvstr}::{e.pkg.repo.repo_id}: {error}')

    if not pkgs:
        argparser.error(f"no matches: {token!r}")

    pkg = max(pkgs)
    if len(pkgs) > 1:
        argparser.err.write(f"got multiple matches for {token!r}:")
        if len(set((p.slot, p.repo) for p in pkgs)) != 1:
            for p in pkgs:
                repo_id = getattr(p.repo, 'repo_id', 'unknown')
                argparser.err.write(f"{p.cpvstr}:{p.slot}::{repo_id}", prefix='  ')
            argparser.err.write()
            argparser.error("please refine your restriction to one match")
        repo_id = getattr(pkg.repo, 'repo_id', 'unknown')
        argparser.err.write(f"choosing {pkg.cpvstr}:{pkg.slot}::{repo_id}", prefix='  ')
        sys.stderr.flush()

    kwds = {}
    phase_obs = observer.phase_observer(observer.formatter_output(out), options.debug)

    phases = [x for x in options.phase if x != 'clean']
    clean = (len(phases) != len(options.phase))

    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in phases:
            phases.insert(0, "fetch")

    # forcibly run test phase if selected
    force_test = 'test' in phases
    if force_test and 'test' in pkg.iuse:
        pkg.use.add('test')

    # by default turn off startup cleans; we clean by ourselves if
    # told to do so via an arg
    build = domain.build_pkg(
        pkg, failed=True, clean=False, allow_fetching=True,
        observer=phase_obs, force_test=force_test)
    if clean:
        build.cleanup(force=True)
    build._reload_state()

    phase_funcs = [(p, getattr(build, p, None)) for p in phases]
    unknown_phases = [p for p, func in phase_funcs if func is None]
    if unknown_phases:
        argparser.error("unknown phase%s: %s" % (
            pluralism(unknown_phases), ', '.join(map(repr, unknown_phases))))

    try:
        for phase, func in phase_funcs:
            out.write(f'executing phase {phase}')
            func(**kwds)
    except OperationError as e:
        raise ExitException(f"caught exception executing phase {phase}: {e}") from e
