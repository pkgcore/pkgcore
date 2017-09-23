# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.config import basics

pkgcore_plugins = {
    'global_config': [{
        'basic': basics.ConfigSectionFromStringDict({
            'class': 'pkgcore.ebuild.formatter.basic_factory',
            }),
        'pkgcore': basics.ConfigSectionFromStringDict({
            'class': 'pkgcore.ebuild.formatter.pkgcore_factory',
            }),
        'portage': basics.ConfigSectionFromStringDict({
            'class': 'pkgcore.ebuild.formatter.portage_factory',
            'default': 'True',
            }),
        'portage-verbose': basics.ConfigSectionFromStringDict({
            'class': 'pkgcore.ebuild.formatter.portage_verbose_factory',
            }),
        'paludis': basics.ConfigSectionFromStringDict({
            'class': 'pkgcore.ebuild.formatter.paludis_factory',
            }),
    }],
}
