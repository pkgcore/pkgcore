# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

pkgcore_plugins = {
    'triggers':['pkgcore.merge.triggers.%s' % x for x in [
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
