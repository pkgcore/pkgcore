# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
system pkgset based off of profile system collapsing
"""

# yuck. :)
import pkgcore.config.introspect

def SystemSet(profile):
	return frozenset(profile.sys)
SystemSet.pkgcore_config_type = \
	pkgcore.config.introspect.ConfigHint(types={"profile":"section_ref"})
