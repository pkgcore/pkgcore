from ..fs import ops

pkgcore_plugins = {
    'fs_ops.copyfile': [ops.default_copyfile],
    'fs_ops.ensure_perms': [ops.default_ensure_perms],
    'fs_ops.mkdir': [ops.default_mkdir],
    'fs_ops.merge_contents': [ops.merge_contents],
    'fs_ops.unmerge_contents': [ops.unmerge_contents],
}
