#!/usr/bin/env python
# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2007 Charlie Shepherd <masterdriverz@gmail.com>
# License: BSD/GPL-2

import sys
from os.path import basename

from snakeoil.osutils import listdir_files, pjoin
from snakeoil.lists import iflatten_instance
from snakeoil.currying import partial


try:
    from pkgcore.util import commandline
    from pkgcore.restrictions import packages
    from pkgcore.restrictions.boolean import OrRestriction
    from pkgcore.repository.multiplex import tree as multiplex_tree
    from pkgcore.fetch import fetchable as fetchable_kls
    from pkgcore.chksum.errors import ParseChksumError
    from pkgcore.util.repo_utils import get_virtual_repos
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
        commandline.OptionParser.__init__(self, description=__doc__, **kwargs)
        self.add_option("--exclude", "-e", action='append', dest='excludes')
        self.add_option("--exclude-file", "-E", action='callback', dest='excludes',
            callback=commandline.read_file_callback, type="string",
            help='path to the exclusion file')
        self.add_option("--ignore-failures", "-i", action="store_true",
            default=False, help="ignore checksum parsing errors")

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)

        if args:
            self.error("This script takes no arguments")
        domain = values.config.get_default('domain')
        values.vdb = domain.vdb
        values.repo = multiplex_tree(*get_virtual_repos(domain.repos, False))
        values.distdir = domain.fetcher.distdir
        restrict = commandline.convert_to_restrict(values.excludes, default=None)
        if restrict != [None]:
            values.restrict = OrRestriction(negate=True, *restrict)
        else:
            values.restrict = packages.AlwaysTrue

        return values, ()

def main(options, out, err):
    if options.debug:
        out.write('starting scanning distdir %s...' % options.distdir)
    files = set(basename(file) for file in listdir_files(options.distdir))

    if options.debug:
        out.write('scanning repo...')

    pfiles = set()
    for pkg in options.repo.itermatch(options.restrict, sorter=sorted):
        try:
            pfiles.update(fetchable.filename for fetchable in
                        iflatten_instance(pkg.fetchables, fetchable_kls))
        except ParseChksumError, e:
            err.write("got corruption error '%s', with package %s " %
                (e, pkg.cpvstr))
            if options.ignore_failures:
                err.write("skipping...")
                err.write()
            else:
                err.write("aborting...")
                return 1
        except Exception, e:
            err.write("got error '%s', parsing package %s in repo '%s'" %
                (e, pkg.cpvstr, pkg.repo))
            raise

    d = options.distdir
    for file in (files - pfiles):
        out.write(pjoin(d, file))

if __name__ == '__main__':
    commandline.main({None: (OptionParser, main)})
