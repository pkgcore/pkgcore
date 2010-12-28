# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


"""Version information (tied to bzr)."""

__all__ = ("get_version",)

from pkgcore import const
from snakeoil.version import get_git_version

_ver = None

def get_version():
    """:return: a string describing the snakeoil version."""
    global _ver
    if _ver is not None:
        return _ver

    try:
        from pkgcore._verinfo import version_info
    except ImportError:
        version_info = get_git_version(__file__)

    _ver = 'pkgcore %s\n(%s)' % (const.VERSION, version_info)

    return _ver
