# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Update the plugin cache."""

__all__ = ("argparser", "main")

from pkgcore.util import commandline
from pkgcore import plugin, plugins
from snakeoil import lists, currying

argparser = commandline.mk_argparser(config=False, domain=False, color=False,
    description = __doc__)
argparser.add_argument("packages", nargs="*", action='store',
    type=currying.partial(commandline.python_namespace_type, module=True),
    default=[plugins],
    help="python namespace(s) to regenerate plugins for.  If none are "
    "specified, pkgcore.plugins is updated")

@argparser.bind_main_func
def main(options, out, err):
    """Update caches."""
    if not options.packages:
        from pkgcore import plugins
        options.packages = [plugins]
    for package in lists.stable_unique(options.packages):
        out.write('Updating cache for %s...' % (package.__name__,))
        plugin.initialize_cache(package)

