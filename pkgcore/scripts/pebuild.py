# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Low-level ebuild operations."""


from pkgcore.util import commandline
from pkgcore.ebuild import atom, errors


class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog [options] atom phases',
            **kwargs)
        self.add_option("--no-auto", action='store_true', default=False,
            help="run just the specified phases.  may explode.")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if len(args) < 2:
            self.error('Specify an atom and at least one phase.')
        try:
            values.atom = atom.atom(args[0])
        except errors.MalformedAtom, e:
            self.error(str(e))
        values.phases = args[1:]
        return values, ()

def main(options, out, err):
    pkgs = options.config.get_default('domain').all_repos.match(options.atom)
    if not pkgs:
        err.write('got no matches for %s\n' % (options.atom,))
        return 1
    if len(pkgs) > 1:
        err.write('got multiple matches for %s: %s\n' % (options.atom, pkgs))
        return 1
    # pull clean out.
    l = list(x for x in options.phases if x != "clean")
    clean = len(l) != len(options.phases)
    if clean:
        options.phases = l
    kwds = {}
    if options.no_auto:
        kwds["ignore_deps"] = True
        if "setup" in l:
            options.phases.insert(0, "fetch")
    build = pkgs[0].build(clean=clean)
    phase_funcs = list(getattr(build, x) for x in options.phases)
    for phase, f in zip(options.phases, phase_funcs):
        out.write()
        out.write('executing phase %s' % (phase,))
        f(**kwds)
