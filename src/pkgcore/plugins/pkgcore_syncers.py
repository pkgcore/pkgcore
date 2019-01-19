# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

pkgcore_plugins = {
    'syncer': [f'pkgcore.sync.{x}.{x}_syncer' for x in
               ('bzr', 'cvs', 'darcs', 'git', 'git_svn', 'hg', 'http', 'sqfs', 'svn')],
}
