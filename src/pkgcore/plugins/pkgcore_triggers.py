pkgcore_plugins = {
    'triggers': [f'pkgcore.merge.triggers.{x}' for x in [
        'ldconfig',
        'merge',
        'unmerge',
        'fix_uid_perms',
        'fix_gid_perms',
        'fix_set_bits',
        'detect_world_writable',
        'InfoRegen',
        'CommonDirectoryModes',
        'BaseSystemUnmergeProtection',
    ]],
}
