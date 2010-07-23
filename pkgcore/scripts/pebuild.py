# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Low-level ebuild operations."""


from pkgcore.util import commandline
from pkgcore.ebuild import atom, errors
from pkgcore.operations import observer
from snakeoil.formatters import ObserverFormatter


class OptionParser(commandline.OptionParser):

    description = __doc__
    usage = '%prog [options] atom phases'

    def _register_options(self):
        self.add_option("--no-auto", action='store_true', default=False,
            help="run just the specified phases.  may explode.")

    def _check_values(self, values, args):
        if len(args) < 2:
            self.error('Specify an atom and at least one phase.')
        try:
            values.atom = atom.atom(args[0])
        except errors.MalformedAtom, e:
            self.error(str(e))
        values.phases = args[1:]
        return values, ()


def main(options, out, err):
    domain = options.config.get_default('domain')
    pkgs = domain.all_repos.match(options.atom)
    if not pkgs:
        err.write('got no matches for %s\n' % (options.atom,))
        return 1
    if len(pkgs) > 1:
        err.write('got multiple matches for %s: %s\n' % (options.atom, pkgs))
        return 1
    kwds = {}
    build_obs = observer.file_build_observer(ObserverFormatter(out),
        not options.debug)

    phases = [x for x in options.phases if x != 'clean']
    clean = (len(phases) != len(options.phases))

    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in phases:
            phases.insert(0, "fetch")
    # by default turn off startup cleans; we clean by ourselves if
    # told to do so via an arg
    build = domain.build_pkg(pkgs[0], build_obs, clean=False)
    if clean:
        build.cleanup(force=True)
    build._reload_state()
    phase_funcs = list(getattr(build, x) for x in phases)
    for phase, f in zip(phases, phase_funcs):
        out.write()
        out.write('executing phase %s' % (phase,))
        f(**kwds)
