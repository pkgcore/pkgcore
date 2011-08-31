# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Clone a repository cache."""

__all__ = ("argparser", "main")

import time

from pkgcore.util import commandline

argparser = commandline.mk_argparser(domain=False, description=__doc__)
argparser.add_argument("--verbose", "-v", action='store_true',
    help="print keys as they are processed")
argparser.add_argument("source", config_type='cache',
    action=commandline.StoreConfigObject,
    help="source cache to copy data from")
argparser.add_argument("target", config_type='cache',
    action=commandline.StoreConfigObject, writable=True,
    help="target cache to update.  Must be writable.")

@argparser.bind_main_func
def main(options, out, err):
    import pdb;pdb.set_trace()
    if options.target.readonly:
        self.error("can't update cache label '%s', it's marked readonly." %
        (options.target,))

    source, target = options.source, options.target
    if not target.autocommits:
        target.sync_rate = 1000
    if options.verbose:
        out.write("grabbing target's existing keys")
    valid = set()
    start = time.time()
    if options.verbose:
        for k, v in source.iteritems():
            out.write("updating %s" % (k,))
            target[k] = v
            valid.add(k)
    else:
        for k, v in source.iteritems():
            target[k] = v
            valid.add(k)

    for x in target.iterkeys():
        if not x in valid:
            if options.verbose:
                out.write("deleting %s" % (x,))
            del target[x]

    if options.verbose:
        out.write("took %i seconds" % int(time.time() - start))
