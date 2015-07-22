# Copyright: 2010-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2


"""Version information (tied to git)."""

__all__ = ("get_version",)

from pkgcore import __version__

_ver = None


def _compatibility_version():
    version_info = None
    try:
        from pkgcore._verinfo import version_info
    except ImportError:
        return "pkgcore %s\nUnknown vcs version" % (__version__,)
    if not isinstance(version_info, str):
        return (
            "pkgcore %s\ngit rev %s, date %s" %
            (__version__, version_info['rev'], version_info['date']))
    return "pkgcore %s\n%s" % (__version__, version_info)

def get_version():
    """:return: a string describing the pkgcore version."""
    global _ver
    if _ver is None:
        try:
            from snakeoil.version import format_version
        except ImportError:
            format_version = None
        if format_version is None:
            _ver = _compatibility_version()
        else:
            _ver = format_version('pkgcore', __file__, __version__)
    return _ver
