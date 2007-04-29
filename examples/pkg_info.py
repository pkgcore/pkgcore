#! /usr/bin/env python

import sys, itertools

try:
    from pkgcore.util import commandline, parserestrict
    from pkgcore.restrictions.packages import AlwaysTrue
    from pkgcore.restrictions.boolean import OrRestriction
except ImportError:
    print >> sys.stderr, 'Cannot import pkgcore!'
    print >> sys.stderr, 'Verify it is properly installed and/or ' \
        'PYTHONPATH is set correctly.'
    if '--debug' not in sys.argv:
        print >> sys.stderr, 'Add --debug to the commandline for a traceback.'
    else:
        raise
    sys.exit(1)

class OptionParser(commandline.OptionParser):
    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog <atom>',
            **kwargs)
    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        values.repo = values.config.get_default('domain').repos[1]
        values.restrict = OrRestriction(*commandline.convert_to_restrict(args))
        return values, ()

def getter(pkg):
    return (pkg.key, getattr(pkg, "maintainers", None),
            getattr(pkg, "herds", None))

def main(options, out, err):
    for t, pkgs in itertools.groupby(
        options.repo.itermatch(options.restrict, sorter=sorted), getter):
        out.write(t[0])
        out.first_prefix = "    "
        for pkg in pkgs:
            out.write(pkg.cpvstr)
        out.first_prefix = ""
        out.write()
        for item, values in zip(("maintainer", "herd"), t[1:]):
            if values:
                out.write("%s(s): %s" %
                    (item.title(), ', '.join((unicode(x) for x in values))))
        out.write()
        out.write()

if __name__ == '__main__':
    commandline.main({None: (OptionParser, main)})
