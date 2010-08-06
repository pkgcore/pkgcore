# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Update the plugin cache."""

__all__ = ("OptionParser", "main")

from pkgcore.util import commandline
from pkgcore import plugin
from snakeoil import modules

class OptionParser(commandline.OptionParser):

    description = __doc__
    usage = '%prog [packages]'

    def _check_values(self, values, args):
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
