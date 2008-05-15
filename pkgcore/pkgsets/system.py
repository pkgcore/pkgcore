# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
system pkgset based off of profile system collapsing
"""

# yuck. :)
from pkgcore.config import configurable

@configurable({'profile': 'ref:profile'}, typename='pkgset')
def SystemSet(profile):
    return frozenset(profile.system)
