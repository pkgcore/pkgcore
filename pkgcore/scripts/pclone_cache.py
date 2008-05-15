# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>: BSD/GPL2
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Clone a repository cache."""


import time

from pkgcore.util import commandline


class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog [options] source target',
            **kwargs)
        self.add_option('--verbose', '-v', action='store_true',
                        help='print keys as they are processed')

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if len(args) != 2:
            self.error(
                'Need two arguments: cache label to read from and '
                'cache label to write to.')

        config = values.config
        try:
            values.source = config.cache[args[0]]
        except KeyError:
            self.error("read cache label '%s' isn't defined." % (args[0],))
        try:
            values.target = config.cache[args[1]]
        except KeyError:
            self.error("write cache label '%s' isn't defined." % (args[1],))

        if values.target.readonly:
            self.error("can't update cache label '%s', it's marked readonly." %
                       (args[1],))

        return values, ()


def main(options, out, err):
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
