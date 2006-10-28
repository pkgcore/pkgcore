# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Update the plugin cache."""


from pkgcore.util import commandline, modules
from pkgcore import plugin


class OptionParser(commandline.OptionParser):

    def __init__(self, **kwargs):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog [packages]', **kwargs)

    def check_values(self, values, args):
        """Sanity check and postprocess after parsing."""
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if not args:
            args = ['pkgcore.plugins']
        values.packages = []
        for arg in args:
            try:
                package = modules.load_module(arg)
            except modules.FailedImport, e:
                self.error('Failed to import %s (%s)' % (arg, e))
            if not getattr(package, '__path__', False):
                self.error('%s is not a package' % (arg,))
            values.packages.append(package)
        return values, ()


def main(options, out, err):
    """Update caches."""
    for package in options.packages:
        out.write('Updating cache for %s...' % (package.__name__,))
        plugin.initialize_cache(package)
