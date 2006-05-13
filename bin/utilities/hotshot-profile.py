#!/usr/bin/python
from optparse import OptionParser
import sys, os
import hotshot

# When invoked as main program, invoke the profiler on a script
if __name__ == '__main__':
    usage = "hotshot.py [-o output_file_path] [-s sort] scriptfile [arg] ..."
    if not sys.argv[1:]:
        print "Usage: ", usage
        sys.exit(2)

    class ProfileParser(OptionParser):
        def __init__(self, usage):
            OptionParser.__init__(self)
            self.usage = usage

    parser = ProfileParser(usage)
    parser.allow_interspersed_args = False
    parser.add_option('-o', '--outfile', dest="outfile",
        help="Save stats to <outfile>", default=None)
    parser.add_option('-s', '--sort', dest="sort",
        help="Sort order when printing to stdout, based on pstats.Stats class", default=-1)

    (options, args) = parser.parse_args()
    sys.argv[:] = args

    if (len(sys.argv) > 0):
        sys.path.insert(0, os.path.dirname(sys.argv[0]))
        prof = hotshot.Profile(options.outfile)
        prof.run('execfile(%r)' % (sys.argv[0],)) #, options.outfile, options.sort)
        prof.close()
    else:
        print "Usage: ", usage
