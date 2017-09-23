# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""low-level ebuild utility"""

from itertools import izip
import os

from pkgcore.ebuild import atom
from pkgcore.ebuild.errors import MalformedAtom
from pkgcore.operations import observer, format
from pkgcore.util import commandline

from snakeoil.strings import pluralism


argparser = commandline.ArgumentParser(
    description=__doc__, script=(__file__, __name__))
argparser.add_argument(
    'target', metavar='<atom|ebuild>',
    help="atom or ebuild matching a pkg to execute phases from")
argparser.add_argument('phase', nargs='+', help="phases to run")
phase_opts = argparser.add_argument_group("phase options")
phase_opts.add_argument(
    "--no-auto", action='store_true', default=False,
    help="run just the specified phases; "
         "it's up to the invoker to get the order right")


@argparser.bind_final_check
def _validate_args(parser, namespace):
    target = namespace.target
    repo = namespace.domain.ebuild_repos_raw

    if target.endswith('.ebuild'):
        if not os.path.exists(target):
            parser.error("nonexistent ebuild: %r" % target)
        elif not os.path.isfile(target):
            parser.error("invalid ebuild: %r" % target)
        try:
            restriction = repo.path_restrict(target)
        except ValueError as e:
            parser.error(e)
    else:
        try:
            restriction = atom.atom(target)
        except MalformedAtom:
            if os.path.isfile(target):
                parser.error("file not an ebuild: %r" % target)
            else:
                parser.error("invalid package atom: %r" % target)

    pkgs = repo.match(restriction)
    if not pkgs:
        parser.error("no matches: %r" % (target,))

    pkg = max(pkgs)
    if len(pkgs) > 1:
        parser.err.write("got multiple matches for %r:" % (target,))
        if len(set((p.slot, p.repo) for p in pkgs)) != 1:
            for p in pkgs:
                parser.err.write(
                    "%s:%s::%s" % (p.cpvstr, p.slot,
                                   getattr(p.repo, 'repo_id', 'unknown')), prefix='  ')
            parser.err.write()
            parser.error("please refine your restriction to one match")
        parser.err.write(
            "choosing %s:%s::%s" %
            (pkg.cpvstr, pkg.slot, getattr(pkg.repo, 'repo_id', 'unknown')), prefix='  ')

    namespace.pkg = pkg


@argparser.bind_main_func
def main(options, out, err):
    domain = options.domain

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
    build = domain.build_pkg(options.pkg, phase_obs, clean=False, allow_fetching=True)
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
            out.write('executing phase %s' % (phase,))
            func(**kwds)
    except format.errors as e:
        out.error("caught exception executing phase %s: %s" % (phase, e))
        return 1
