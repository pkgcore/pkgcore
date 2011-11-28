# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

pkgcore_plugins = {
    'syncer': ['pkgcore.sync.%s.%s_syncer' % (x, x) for x in
            ('bzr', 'cvs', 'darcs', 'git','hg', 'svn')
        ],
    }
