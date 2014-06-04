# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Low-level ebuild operations."""

__all__ = ("argparser", "main")

from itertools import izip

from pkgcore.util import commandline
from pkgcore.ebuild import atom
from pkgcore.operations import observer


argparser = commandline.mk_argparser(description=__doc__)
argparser.add_argument("--no-auto", action='store_true', default=False,
    help="run just the specified phases; it's up to the invoker to get the order right")
argparser.add_argument('atom', type=atom.atom,
    help="atom to match a pkg to execute phases from")
argparser.add_argument('phase', nargs='+',
    help="phases to run")

@argparser.bind_main_func
def main(options, out, err):
    pkgs = options.domain.all_repos.match(options.atom)
    if not pkgs:
        err.write('got no matches for %s\n' % (options.atom,))
        return 1
    if len(pkgs) > 1:
        err.write('got multiple matches for %s:' % (options.atom,))
        if len(set((pkg.slot, pkg.repo) for pkg in pkgs)) != 1:
            for pkg in sorted(pkgs):
                err.write("repo %r, slot %r, %s" %
                    (getattr(pkg.repo, 'repo_id', 'unknown'), pkg.slot, pkg.cpvstr,), prefix="  ")
            err.write()
            err.write("please refine your restriction to match only one slot/repo pair\n");
            return 1
        pkgs = [max(pkgs)]
        err.write("choosing %r, slot %r, %s" % (getattr(pkgs[0].repo, 'repo_id', 'unknown'),
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
        out.write()
        out.write('executing phase %s' % (phase,))
        f(**kwds)
