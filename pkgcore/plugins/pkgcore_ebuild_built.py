# Copyright: 2007 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.ebuild import ebuild_built

pkgcore_plugins = {
    'format.ebuild_built': [ebuild_built.generate_new_factory],
    }
