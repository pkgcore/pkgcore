#!/usr/bin/env python3

import itertools
import sys

try:
    from pkgcore.restrictions.boolean import OrRestriction
    from pkgcore.util import commandline
except ImportError:
    print('Cannot import pkgcore!', file=sys.stderr)
    print('Verify it is properly installed and/or PYTHONPATH is set correctly.', file=sys.stderr)
    if '--debug' not in sys.argv:
        print('Add --debug to the commandline for a traceback.', file=sys.stderr)
    else:
        raise
    sys.exit(1)


argparser = commandline.ArgumentParser(color=False, version=False)
argparser.add_argument(
    'target', nargs='+', help='target package atoms')


@argparser.bind_final_check
def check_args(parser, namespace):
    namespace.repo = namespace.domain.ebuild_repos
    namespace.restrict = OrRestriction(
        *commandline.convert_to_restrict(namespace.target))


def getter(pkg):
    return (pkg.key, getattr(pkg, "maintainers", None))


@argparser.bind_main_func
def main(options, out, err):
    for t, pkgs in itertools.groupby(
            options.repo.itermatch(options.restrict, sorter=sorted), getter):
        out.write(t[0])
        out.first_prefix = "    "
        for pkg in pkgs:
            out.write('%s::%s' % (pkg.cpvstr, pkg.repo.repo_id))
        out.first_prefix = ""
        item = 'maintainer'
        values = t[1]
        if values:
            out.write(
                "%s%s: %s" %
                (item.title(), 's'[len(values) == 1:], ', '.join(str(x) for x in values)))
        out.write()

if __name__ == '__main__':
    commandline.main(argparser)
