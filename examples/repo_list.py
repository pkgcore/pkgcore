#!/usr/bin/env python

# Copyright 2007 Charlie Shepherd

import sys

try:
    from pkgcore.util import commandline
    from pkgcore.util.repo_utils import get_raw_repos, get_virtual_repos
except ImportError:
    print >> sys.stderr, 'Cannot import pkgcore!'
    print >> sys.stderr, 'Verify it is properly installed and/or ' \
        'PYTHONPATH is set correctly.'
    print >> sys.stderr, 'Add --debug to the commandline for a traceback.'
    if '--debug' in sys.argv:
        raise
    sys.exit(1)

class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog [options]',
            **kwargs)
        self.add_option("--repo", "-r", action='callback', type='string',
            callback=commandline.config_callback, callback_args=('repo',),
            help='repo to give info about (default from domain if omitted)')

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        if args: self.error("This script takes no arguments")

        # Get repo(s) to operate on.
        if values.repo:
            repos = (values.repo,)
        else:
            repos = values.config.get_default('domain').repos
        values.repos = get_virtual_repos(get_raw_repos(repos), False)

        return values, ()

def main(options, out, err):
    for repo in options.repos:
        out.write("Repo ID: %s" % repo.repo_id)
        location = getattr(repo, "location", None)
        if location:
            out.write("Repo location: %s" % location)
        else:
            out.write("Repo has no on-disk location")
        out.write("%d packages" % len(repo.versions))
        out.write("%d categories" % len(repo.packages))
        out.write()

if __name__ == '__main__':
    commandline.main({None: (OptionParser, main)})
