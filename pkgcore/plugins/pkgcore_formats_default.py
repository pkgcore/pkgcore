# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.ebuild import ebuild_built, ebuild_src

pkgcore_plugins = {
    'format.ebuild_built': [ebuild_built.generate_new_factory],
    'format.ebuild_src': [ebuild_src.generate_new_factory],
    }
