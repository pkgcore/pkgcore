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
    'target', metavar='<atom|ebuild>',
    help="atom or ebuild matching a pkg to execute phases from")
argparser.add_argument('phase', nargs='+', help="phases to run")
phase_opts = argparser.add_argument_group("phase options")
phase_opts.add_argument(
    "--no-auto", action='store_true', default=False,
    help="run just the specified phases; "
         "it's up to the invoker to get the order right")


@argparser.bind_main_func
def main(options, out, err):
    target = options.target
    domain = options.domain

    if os.path.isfile(target):
        if not target.endswith('.ebuild'):
            err.write("file not an ebuild: '%s'" % target)
            return 1

        try:
            restriction = domain.ebuild_repos.path_restrict(target)
        except ValueError:
            err.write("no configured ebuild repo contains: '%s'" % target)
            return 1
    else:
        try:
            restriction = atom.atom(target)
        except MalformedAtom:
            err.write("not a valid atom or ebuild: '%s'" % target)
            return 1

    pkgs = domain.ebuild_repos.match(restriction)
    if not pkgs:
        err.write("no matches for '%s'" % (target,))
        return 1

    pkg = max(pkgs)
    if len(pkgs) > 1:
        err.write("got multiple matches for '%s':" % (target,))
        if len(set((p.slot, p.repo) for p in pkgs)) != 1:
            for p in pkgs:
                err.write(
                    "%s:%s::%s" % (p.cpvstr, p.slot,
                                   getattr(p.repo, 'repo_id', 'unknown')), prefix='  ')
            err.write()
            err.write("please refine your restriction to one match")
            return 1
        err.write(
            "choosing %s:%s::%s" %
            (pkg.cpvstr, pkg.slot, getattr(pkg.repo, 'repo_id', 'unknown')), prefix='  ')

    kwds = {}
    phase_obs = observer.phase_observer(observer.formatter_output(out),
                                        not options.debug)

    phases = [x for x in options.phase if x != 'clean']
    clean = (len(phases) != len(options.phase))

    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in phases:
            phases.insert(0, "fetch")
    # by default turn off startup cleans; we clean by ourselves if
    # told to do so via an arg
    build = domain.build_pkg(pkg, phase_obs, clean=False, allow_fetching=True)
    if clean:
        build.cleanup(force=True)
    build._reload_state()
    phase_funcs = (getattr(build, x) for x in phases)
    for phase, f in izip(phases, phase_funcs):
        out.write('executing phase %s' % (phase,))
        f(**kwds)
