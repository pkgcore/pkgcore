# Copyright: 2010-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2


"""Version information (tied to git)."""

__all__ = ("get_version",)

from pkgcore import const

_ver = None

def get_version():
    """:return: a string describing the pkgcore version."""
    global _ver
    if _ver is not None:
        return _ver

    try:
        from pkgcore._verinfo import version_info
    except ImportError:
        # intentionally lazy imported.
        from snakeoil.version import get_git_version
        version_info = get_git_version(__file__)

    _ver = 'pkgcore %s\n(%s)' % (const.VERSION, version_info)

    return _ver
