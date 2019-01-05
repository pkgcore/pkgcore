# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""low-level ebuild utility"""

import os
import sys

from pkgcore.ebuild import atom
from pkgcore.ebuild.errors import MalformedAtom
from pkgcore.operations import observer, format
from pkgcore.util.commandline import ArgumentParser, StoreTarget

from snakeoil.strings import pluralism


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
    token, restriction = namespace.target[0]
    repo = namespace.domain.ebuild_repos_unfiltered

    pkgs = repo.match(restriction)
    if not pkgs:
        parser.error(f"no matches: {token!r}")

    pkg = max(pkgs)
    if len(pkgs) > 1:
        parser.err.write(f"got multiple matches for {token!r}:")
        if len(set((p.slot, p.repo) for p in pkgs)) != 1:
            for p in pkgs:
                repo_id = getattr(p.repo, 'repo_id', 'unknown')
                parser.err.write(f"{p.cpvstr}:{p.slot}::{repo_id}", prefix='  ')
            parser.err.write()
            parser.error("please refine your restriction to one match")
        repo_id = getattr(pkg.repo, 'repo_id', 'unknown')
        parser.err.write(f"choosing {pkg.cpvstr}:{pkg.slot}::{repo_id}", prefix='  ')
        sys.stderr.flush()

    namespace.pkg = pkg


@argparser.bind_main_func
def main(options, out, err):
    domain = options.domain

    kwds = {}
    phase_obs = observer.phase_observer(
        observer.formatter_output(out), not options.debug)

    phases = [x for x in options.phase if x != 'clean']
    clean = (len(phases) != len(options.phase))

    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in phases:
            phases.insert(0, "fetch")

    # forcibly run test phase if selected
    force_test = 'test' in phases
    if force_test and 'test' in options.pkg.iuse:
        options.pkg.use.add('test')

    # by default turn off startup cleans; we clean by ourselves if
    # told to do so via an arg
    build = domain.build_pkg(
        options.pkg, phase_obs, clean=False, allow_fetching=True, force_test=force_test)
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
    except format.errors as e:
        out.error(f"caught exception executing phase {phase}: {e}")
        return 1
