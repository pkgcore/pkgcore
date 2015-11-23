# Copyright: 2015 Tim Harder <radhermit@gmail.com
# License: BSD/GPL2

"""utililty for keywording ebuilds"""

import argparse

from pkgcore.util import commandline, parserestrict
from pkgcore.repository.util import RepositoryGroup


class StoreTarget(argparse._AppendAction):

    def __call__(self, parser, namespace, values, option_string=None):
        targets = []
        try:
            for x in values:
                targets.append((x, parserestrict.parse_match(x)))
        except parserestrict.ParseError as e:
            parser.only_error(e)
        setattr(namespace, self.dest, targets)


argparser = commandline.mk_argparser(description=__doc__)
# TODO: check against valid arch list
argparser.add_argument(
    '-k', '--keyword', action='extend_comma',
    help='keyword changes to make')
argparser.add_argument(
    '-n', '--dry-run',
    help='show changes without running them')
# TODO: force ebuild repos only and allow multi-repo comma-separated input
argparser.add_argument(
    '-r', '--repo',
    action=commandline.StoreRepoObject, priority=29,
    help='repo(s) to use (defaults to all ebuild repos)')
argparser.add_argument(
    'targets', metavar='target', nargs='+', action=StoreTarget,
    help="extended atom matching of packages")


@argparser.bind_delayed_default(30, 'repos')
def setup_repos(namespace, attr):
    # Get repo(s) to operate on.
    if namespace.repo:
        repo = RepositoryGroup([namespace.repo.raw_repo])
    else:
        repo = namespace.domain.ebuild_repos_raw

    namespace.repo = repo


@argparser.bind_final_check
def _validate_args(parser, namespace):
    pass


@argparser.bind_main_func
def main(options, out, err):
    for token, restriction in options.targets:
        pkgs = options.repo.match(restriction)

        if not pkgs:
            err.write("no matches for '%s'" % (token,))
            continue

        for pkg in pkgs:
            out.write('TODO: actually write changes to %s' % (pkg.cpvstr))
