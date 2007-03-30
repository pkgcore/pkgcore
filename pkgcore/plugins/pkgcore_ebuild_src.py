# Copyright: 2007 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.ebuild import ebuild_src

pkgcore_plugins = {
    'format.ebuild_src': [ebuild_src.generate_new_factory],
    }
