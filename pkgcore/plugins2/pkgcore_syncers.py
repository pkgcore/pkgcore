# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.sync import bzr, cvs, darcs, git, hg, svn


pkgcore_plugins = {
    'syncer': [
        (bzr.bzr_syncer, False),
        (cvs.cvs_syncer, False),
        (darcs.darcs_syncer, False),
        (git.git_syncer, False),
        (hg.hg_syncer, False),
        (svn.svn_syncer, False),
        ],
    }
