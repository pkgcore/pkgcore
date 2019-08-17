pkgcore_plugins = {
    'syncer': [f'pkgcore.sync.{x}.{x}_syncer' for x in
               ('bzr', 'cvs', 'darcs', 'git', 'git_svn', 'hg', 'sqfs', 'svn', 'tar')],
}
