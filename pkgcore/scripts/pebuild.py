# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""pkgcore low-level ebuild utility"""

__all__ = ("argparser", "main")

from itertools import izip
import os

from pkgcore.ebuild import atom
from pkgcore.ebuild.errors import MalformedAtom
from pkgcore.operations import observer
from pkgcore.util import commandline

argparser = commandline.mk_argparser(description=__doc__.split('\n', 1)[0])
argparser.add_argument(
    "--no-auto", action='store_true', default=False,
    help="run just the specified phases; "
         "it's up to the invoker to get the order right")
argparser.add_argument(
    'pkg', metavar='<atom|ebuild>',
    help="atom or ebuild matching a pkg to execute phases from")
argparser.add_argument('phase', nargs='+', help="phases to run")


@argparser.bind_main_func
def main(options, out, err):
    pkg = options.pkg
    repos = None

    if os.path.isfile(pkg) and pkg.endswith('.ebuild'):
        ebuild_path = os.path.abspath(pkg)
        repo_path = os.path.abspath(os.path.join(
            pkg, os.pardir, os.pardir, os.pardir))

        # find the ebuild's repo
        # TODO: iterating through the repos feels wrong, we could use a
        # multi-keyed dict with repo IDs and paths as keys with repo
        # objects as values (same thing we need for better portage-2
        # profile support)
        for x in options.domain.repos:
            if getattr(x, 'repository_type', None) == 'source' and \
                    x.raw_repo.location == repo_path:
                repos = x
                break

        if repos is None:
            err.write('no configured repo contains: %s' % ebuild_path)
            return 1

        ebuild_P = os.path.basename(os.path.splitext(ebuild_path)[0])
        ebuild_category = ebuild_path.split(os.sep)[-3]
        pkg = atom.atom('=%s/%s' % (ebuild_category, ebuild_P))
    else:
        try:
            pkg = atom.atom(pkg)
            repos = options.domain.all_repos
        except MalformedAtom:
            err.write('not a valid atom or ebuild: "%s"' % pkg)
            return 1

    pkgs = repos.match(pkg)
    if not pkgs:
        err.write('got no matches for %s\n' % (pkg,))
        return 1
    if len(pkgs) > 1:
        err.write('got multiple matches for %s:' % (pkg,))
        if len(set((pkg.slot, pkg.repo) for pkg in pkgs)) != 1:
            for pkg in sorted(pkgs):
                err.write("repo %r, slot %r, %s" %
                          (getattr(pkg.repo, 'repo_id', 'unknown'),
                           pkg.slot, pkg.cpvstr,), prefix="  ")
            err.write()
            err.write("please refine your restriction to match only one slot/repo pair\n")
            return 1
        pkgs = [max(pkgs)]
        err.write("choosing %r, slot %r, %s" %
                  (getattr(pkgs[0].repo, 'repo_id', 'unknown'),
                   pkgs[0].slot, pkgs[0].cpvstr), prefix='  ')

    kwds = {}
    build_obs = observer.build_observer(observer.formatter_output(out),
                                        not options.debug)

    phases = [x for x in options.phase if x != 'clean']
    clean = (len(phases) != len(options.phase))

    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in phases:
            phases.insert(0, "fetch")
    # by default turn off startup cleans; we clean by ourselves if
    # told to do so via an arg
    build = options.domain.build_pkg(pkgs[0], build_obs, clean=False, allow_fetching=True)
    if clean:
        build.cleanup(force=True)
    build._reload_state()
    phase_funcs = (getattr(build, x) for x in phases)
    for phase, f in izip(phases, phase_funcs):
        out.write('executing phase %s' % (phase,))
        f(**kwds)
