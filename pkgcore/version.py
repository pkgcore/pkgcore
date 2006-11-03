# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Version information (tied to bzr)."""


from pkgcore import const


_ver = None


def get_version():
    """@returns: a string describing the pkgcore version."""
    global _ver
    if _ver is not None:
        return _ver

    try:
        from pkgcore.bzr_verinfo import version_info
    except ImportError:
        try:
            from bzrlib import branch, errors
        except ImportError:
            ver = 'unknown (not from an sdist tarball, bzr unavailable)'
        else:
            try:
                # Returns a (branch, relpath) tuple, ignore relpath.
                b = branch.Branch.open_containing(__file__)[0]
            except errors.NotBranchError:
                ver = 'unknown (not from an sdist tarball, not a bzr branch)'
            else:
                ver = '%s:%s %s' % (b.nick, b.revno(), b.last_revision())
    else:
        ver = '%(branch_nick)s:%(revno)s %(revision_id)s' % version_info

    _ver = 'pkgcore %s\n(bzr rev %s)' % (const.VERSION, ver)

    return _ver
