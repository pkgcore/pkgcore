# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.sync import bzr, cvs, darcs, git, hg, svn


pkgcore_plugins = {
    'syncer': [
        bzr.bzr_syncer,
        cvs.cvs_syncer,
        darcs.darcs_syncer,
        git.git_syncer,
        hg.hg_syncer,
        svn.svn_syncer,
        ],
    }
