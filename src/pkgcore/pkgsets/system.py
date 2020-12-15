"""
system pkgset based off of profile system collapsing
"""

__all__ = ("SystemSet",)

from ..config.hint import ConfigHint


class SystemSet:
    """Set of packages defined by the selected profile."""
    pkgcore_config_type = ConfigHint({'profile': 'ref:profile'}, typename='pkgset')

    def __init__(self, profile):
        self.system = frozenset(profile.system)

    def __iter__(self):
        for pkg in self.system:
            yield pkg
