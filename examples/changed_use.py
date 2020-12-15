#!/usr/bin/env python3
# Copyright 2007 Charlie Shepherd

import os
import sys
from operator import attrgetter

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
argparser.add_argument(
    '--repo', action=commandline.StoreRepoObject,
    help='repo to use (default from domain if omitted).')
argparser.add_argument(
    '--print_type', '-t', default="cpvstr",
    choices=("slotted_atom", "versioned_atom", "cpvstr"),
    help='''type of atom to output:
                'versioned_atom' : a valid versioned atom,
                'slotted_atom'   : a valid slotted atom,
                'cpvstr'         : the cpv of the package''')


@argparser.bind_final_check
def check_args(parser, namespace):
    domain = namespace.domain
    namespace.vdb = domain.all_installed_repos
    if not namespace.repo:
        # fallback to default repo
        namespace.repo = namespace.config.get_default('repo')

    namespace.restrict = OrRestriction(
        *commandline.convert_to_restrict(namespace.target))
    namespace.outputter = attrgetter(namespace.print_type)


@argparser.bind_main_func
def main(options, out, err):
    repo = options.repo
    for built in options.vdb.itermatch(options.restrict):
        current = repo.match(built.unversioned_atom)
        if current:
            current = current[0]
            oldflags = built.iuse & built.use
            newflags = current.iuse & built.use
            if (newflags != oldflags) or (current.iuse ^ built.iuse):
                changed_flags = (oldflags ^ newflags) | (current.iuse ^ built.iuse)
                if options.verbosity > 0:
                    out.write(
                        "package %s, %d flags have changed:\n\t%s" %
                        (current.unversioned_atom, len(changed_flags), ' '.join(changed_flags)))
                else:
                    out.write(options.outputter(current))
            else:
                if options.verbosity > 0:
                    out.write("%s is the same as it was before" % current.cpvstr)

if __name__ == '__main__':
    commandline.main(argparser)
