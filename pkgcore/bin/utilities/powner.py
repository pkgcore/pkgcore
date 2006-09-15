#!/usr/bin/python

import sys, time
from pkgcore.restrictions import packages, values
from pkgcore.config import load_config
from pkgcore.util.osutils import normpath

def grab_arg(arg, args):
    val = False
    try:
        while True:
            args.remove(arg)
            val = True
    except ValueError:
        pass
    return val

if __name__ == "__main__":
    a = sys.argv[1:]
    if grab_arg("--help", a) or grab_arg("-h", a) or not a:
        print "need at least one arg, file to find the owner of"
        print "default matching mode is return after first match, however if [ --all || -a ] is specified"
        print "all owners are return"
        print "Multiple args are further restrictions on a match- pkg must own all of the files"
        sys.exit(1)
    all = grab_arg("-a", a) or grab_arg("--all", a)
    repo = load_config().get_default("domain").vdb[0]
    restrict = packages.PackageRestriction("contents", values.ContainmentMatch(
        *[normpath(x) for x in a]))
    start_time = time.time()
    count = 0
    print "query- %s, returning all matches? %s" % (restrict, all)
    for pkg in repo.itermatch(restrict):
        print "pkg: %s" % (pkg)
        count += 1
        if not all:
            break
    print "found %i matches in %.2f seconds" % (count, time.time() - start_time)
    if count:
        sys.exit(0)
    sys.exit(1)
