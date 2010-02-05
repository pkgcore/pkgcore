# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

from pkgcore.config import basics

pkgcore_plugins = {
    'global_config': [{
            'basic-formatter': basics.ConfigSectionFromStringDict({
                    'class': 'pkgcore.ebuild.formatter.basic_factory',
                    }),
            'pkgcore-formatter': basics.ConfigSectionFromStringDict({
                    'class': 'pkgcore.ebuild.formatter.pkgcore_factory',
                    }),
            'portage-formatter': basics.ConfigSectionFromStringDict({
                    'class': 'pkgcore.ebuild.formatter.portage_factory',
                    'default': 'True',
                    }),
            'paludis-formatter': basics.ConfigSectionFromStringDict({
                    'class': 'pkgcore.ebuild.formatter.paludis_factory',
                    }),
            'portage-verbose-formatter': basics.ConfigSectionFromStringDict({
                    'class':
                        'pkgcore.ebuild.formatter.portage_verbose_factory',
                    }),
            }],
    }
