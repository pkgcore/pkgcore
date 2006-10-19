# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.merge import triggers
from pkgcore.ebuild import triggers as ebuild_triggers

pkgcore_plugins = {
    'triggers':[
        triggers.ldconfig,
        triggers.merge,
        triggers.unmerge,
        triggers.fix_uid_perms,
        triggers.fix_gid_perms,
        triggers.fix_set_bits,
        triggers.detect_world_writable,
        ebuild_triggers.env_update,
        ebuild_triggers.ConfigProtectInstall,
        ebuild_triggers.ConfigProtectUninstall,
        ],
    }
