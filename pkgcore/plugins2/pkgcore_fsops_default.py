# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.fs import ops

pkgcore_plugins = {
    'fs_ops.copyfile': [(ops.default_copyfile, False)],
    'fs_ops.ensure_perms': [(ops.default_ensure_perms, False)],
    'fs_ops.mkdir': [(ops.default_mkdir, False)],
    'fs_ops.merge_contents': [(ops.merge_contents, False)],
    'fs_ops.unmerge_contents': [(ops.unmerge_contents, False)],
    }
