# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
configuration subsystem
"""

# keep these imports as minimal as possible; access to
# pkgcore.config isn't uncommon, thus don't trigger till
# actually needed
from pkgcore.const import GLOBAL_CONF_FILE, SYSTEM_CONF_FILE, USER_CONF_FILE


class ConfigHint(object):

    """hint for introspection supplying overrides"""

    __slots__ = ("types", "positional", "required", "typename", "incrementals",
                 "allow_unknowns")

    def __init__(self, types=None, positional=None, required=None,
                 incrementals=None, typename=None, allow_unknowns=False):
        self.types = types or {}
        self.positional = positional or []
        self.required = required or []
        self.incrementals = incrementals or []
        self.typename = typename
        self.allow_unknowns = allow_unknowns

def configurable(*args, **kwargs):
    """Decorator version of ConfigHint."""
    hint = ConfigHint(*args, **kwargs)
    def decorator(original):
        original.pkgcore_config_type = hint
        return original
    return decorator


def load_config(user_conf_file=USER_CONF_FILE,
                system_conf_file=SYSTEM_CONF_FILE,
                global_conf_file=GLOBAL_CONF_FILE,
                debug=False):
    """
    the main entry point for any code looking to use pkgcore.

    @param user_conf_file: file to attempt to load, else defaults to trying to
        load portage 2 style configs (/etc/make.conf, /etc/make.profile)

    @return: L{pkgcore.config.central.ConfigManager} instance
        representing the system config.
    """

    from pkgcore.config import central, cparser
    import os

    have_system_conf = os.path.isfile(system_conf_file)
    have_user_conf = os.path.isfile(user_conf_file)
    if have_system_conf or have_user_conf:
        configs = []
        if have_user_conf:
            configs.append(cparser.config_from_file(open(user_conf_file)))
        if have_system_conf:
            configs.append(cparser.config_from_file(open(system_conf_file)))
        configs.append(cparser.config_from_file(open(global_conf_file)))
        c = central.ConfigManager(configs, debug=debug)
    else:
        # make.conf...
        from pkgcore.ebuild.portage_conf import config_from_make_conf
        c = central.ConfigManager([config_from_make_conf()], debug=debug)
    return c
