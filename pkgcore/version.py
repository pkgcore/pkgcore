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

    # This should get overwritten below, but let's be paranoid.
    rev = 'unknown revision (internal error)'
    version_info = None
    try:
        from pkgcore.bzr_verinfo import version_info
    except ImportError:
        try:
            from bzrlib import branch, errors
        except ImportError:
            rev = 'unknown revision ' \
                '(not from an sdist tarball, bzr unavailable)'
        else:
            try:
                # Returns a (branch, relpath) tuple, ignore relpath.
                b = branch.Branch.open_containing(__file__)[0]
            except errors.NotBranchError:
                rev = 'unknown revision ' \
                    '(not from an sdist tarball, not a bzr branch)'
            else:
                version_info = {
                    'branch_nick': b.nick,
                    'revno': b.revno(),
                    'revision_id': b.last_revision(),
                    }
                if b.supports_tags():
                    tagdict = b.tags.get_reverse_tag_dict()
                    version_info['tags'] = tagdict.get(b.last_revision())
    if version_info is not None:
        tags = version_info.get('tags')
        if tags:
            revname = ' '.join('tag:%s' % (tag,) for tag in tags)
        else:
            revname = '%(revno)s revid:%(revision_id)s' % version_info
        rev = 'from bzr branch %s %s' % (version_info['branch_nick'], revname)

    _ver = 'pkgcore %s\n%s' % (const.VERSION, rev)

    return _ver
