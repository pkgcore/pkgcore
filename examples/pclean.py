#!/usr/bin/env python
# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2007 Charlie Shepherd <masterdriverz@gmail.com>
# License: BSD/GPL-2

from __future__ import print_function

import argparse
from os.path import basename
import sys

from snakeoil.lists import iflatten_instance
from snakeoil.osutils import listdir_files, pjoin

try:
    from pkgcore.util import commandline
    from pkgcore.restrictions import packages
    from pkgcore.restrictions.boolean import OrRestriction
    from pkgcore.repository.multiplex import tree as multiplex_tree
    from pkgcore.fetch import fetchable as fetchable_kls
    from pkgcore.package.errors import ParseChksumError
    from pkgcore.util.repo_utils import get_virtual_repos
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
    "--exclude", "-e", action='append', dest='excludes')
argparser.add_argument(
    "--exclude-file", "-E",
    type=argparse.FileType('r'),
    help='path to the exclusion file')
argparser.add_argument(
    "--ignore-failures", "-i", action="store_true",
    default=False, help="ignore checksum parsing errors")


@argparser.bind_final_check
def check_args(parser, namespace):
    domain = namespace.domain
    namespace.vdb = domain.vdb
    namespace.repo = multiplex_tree(*get_virtual_repos(domain.repos, False))
    namespace.distdir = domain.fetcher.distdir
    excludes = namespace.excludes if namespace.excludes is not None else []
    if namespace.exclude_file is not None:
        excludes.extend(namespace.exclude_file.read().split('\n'))
    restrict = commandline.convert_to_restrict(excludes, default=None)
    if restrict != [None]:
        namespace.restrict = OrRestriction(negate=True, *restrict)
    else:
        namespace.restrict = packages.AlwaysTrue


@argparser.bind_main_func
def main(options, out, err):
    if options.debug:
        out.write('starting scanning distdir %s...' % options.distdir)
    files = set(basename(file) for file in listdir_files(options.distdir))

    if options.debug:
        out.write('scanning repo...')

    pfiles = set()
    for pkg in options.repo.itermatch(options.restrict, sorter=sorted):
        try:
            pfiles.update(
                fetchable.filename for fetchable in
                iflatten_instance(pkg.fetchables, fetchable_kls))
        except ParseChksumError as e:
            err.write(
                "got corruption error '%s', with package %s " %
                (e, pkg.cpvstr))
            if options.ignore_failures:
                err.write("skipping...")
                err.write()
            else:
                err.write("aborting...")
                return 1
        except Exception as e:
            err.write(
                "got error '%s', parsing package %s in repo '%s'" %
                (e, pkg.cpvstr, pkg.repo))
            raise

    d = options.distdir
    for file in (files - pfiles):
        out.write(pjoin(d, file))

if __name__ == '__main__':
    commandline.main(argparser)
