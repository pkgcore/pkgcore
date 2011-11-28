# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

from pkgcore.ebuild import ebuild_src

pkgcore_plugins = {
    'format.ebuild_src': ['pkgcore.ebuild.ebuild_src.generate_new_factory'],
    'format.ebuild_built': ['pkgcore.ebuild.ebuild_built.generate_new_factory'],
}
