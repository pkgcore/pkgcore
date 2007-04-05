#!/usr/bin/env python

# Copyright 2007 Charlie Shepherd

import sys

try:
    from pkgcore.util import commandline
    from pkgcore.restrictions.boolean import OrRestriction
    from pkgcore.util.repo_utils import get_virtual_repos, get_raw_repos
    from pkgcore.repository.multiplex import tree as multiplex_tree
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
            self, description=__doc__, usage='%prog [options]',
            **kwargs)
        self.add_option('--repo', action='callback', type='string',
            callback=commandline.config_callback,
            callback_args=('repo',),
            help='repo to use (default from domain if omitted).')
        self.add_option('--verbose', '-v', action='store_true', default=False,
            help='print packages that have not changed too')
        self.add_option('--quiet', '-q', action='store_true', default=False,
            help="don't print changed useflags")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        domain = values.config.get_default('domain')
        values.vdb = domain.vdb[0]
        if not values.repo:
            values.repo = domain.repos[1]

        values.restrict = OrRestriction(*commandline.convert_to_restrict(args))
        return values, ()

def main(options, out, err):
    repo = options.repo
    for built in options.vdb.itermatch(options.restrict):
        current = repo.match(built.versioned_atom)
        if current:
            current = current[0]
            oldflags = built.iuse & built.use
            newflags = current.iuse & current.use
            if newflags != oldflags:
                changed_flags = oldflags ^ newflags
                if options.quiet:
                    out.write(current.cpvstr)
                else:
                    out.write("for package %s, %d flags have changed:\n\t%s" %
                          (current.cpvstr, len(changed_flags), ' '.join(changed_flags)))
            else:
                if options.verbose:
                    out.write("%s is the same as it was before" % current.cpvstr)

if __name__ == '__main__':
    commandline.main({None: (OptionParser, main)})
