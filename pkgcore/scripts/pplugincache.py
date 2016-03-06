# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""plugin cache update utility"""

from functools import partial

from snakeoil.sequences import stable_unique

from pkgcore import plugin, plugins
from pkgcore.util import commandline

argparser = commandline.ArgumentParser(
    config=False, domain=False, color=False, description=__doc__)
argparser.add_argument(
    "packages", nargs="*", action='store', default=[plugins],
    type=partial(commandline.python_namespace_type, module=True),
    help="python namespace(s) to regenerate plugins for.  If none are "
         "specified, pkgcore.plugins is updated")


@argparser.bind_main_func
def main(options, out, err):
    """Update caches."""
    for package in stable_unique(options.packages):
        out.write('Updating cache for %s...' % (package.__name__,))
        plugin.initialize_cache(package, force=True)
