# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Update the plugin cache."""

__all__ = ("argparse_parser", "main")

from pkgcore.util import commandline
from pkgcore import plugin, plugins
from snakeoil import modules, lists

def main(options, out, err):
    """Update caches."""
    if not options.packages:
        from pkgcore import plugins
        options.packages = [plugins]
    for package in lists.stable_unique(options.packages):
        out.write('Updating cache for %s...' % (package.__name__,))
        plugin.initialize_cache(package)

argparse_parser = commandline.mk_argparser(config=False, domain=False, color=False,
    description = __doc__)
argparse_parser.add_argument("packages", nargs="*", action='store',
    type=modules.load_module, default=[plugins],
    help="python namespace(s) to regenerate plugins for.  If none are "
    "specified, pkgcore.plugins is updated")
argparse_parser.set_defaults(main_func=main)
