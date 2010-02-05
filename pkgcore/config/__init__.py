# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
configuration subsystem
"""

# keep these imports as minimal as possible; access to
# pkgcore.config isn't uncommon, thus don't trigger till
# actually needed
from pkgcore.const import SYSTEM_CONF_FILE, USER_CONF_FILE

class ConfigHint(object):

    """hint for introspection supplying overrides"""

    # be aware this is used in clone
    __slots__ = (
        "types", "positional", "required", "typename", "allow_unknowns", "doc")

    def __init__(self, types=None, positional=None, required=None, doc=None,
                 typename=None, allow_unknowns=False):
        self.types = types or {}
        self.positional = positional or []
        self.required = required or []
        self.typename = typename
        self.allow_unknowns = allow_unknowns
        self.doc = doc

    def clone(self, **kwds):
        new_kwds = {}
        for attr in self.__slots__:
            new_kwds[attr] = kwds.pop(attr, getattr(self, attr))
        if kwds:
            raise TypeError("unknown type overrides: %r" % kwds)
        return self.__class__(**new_kwds)


def configurable(*args, **kwargs):
    """Decorator version of ConfigHint."""
    hint = ConfigHint(*args, **kwargs)
    def decorator(original):
        original.pkgcore_config_type = hint
        return original
    return decorator


def load_config(user_conf_file=USER_CONF_FILE,
                system_conf_file=SYSTEM_CONF_FILE,
                debug=False, prepend_sources=(), skip_config_files=False):
    """
    the main entry point for any code looking to use pkgcore.

    @param user_conf_file: file to attempt to load, else defaults to trying to
        load portage 2 style configs (/etc/make.conf, /etc/make.profile)

    @return: L{pkgcore.config.central.ConfigManager} instance
        representing the system config.
    """

    from pkgcore.config import central, cparser
    from pkgcore.plugin import get_plugins
    import os

    configs = list(prepend_sources)
    if not skip_config_files:
        have_system_conf = os.path.isfile(system_conf_file)
        have_user_conf = os.path.isfile(user_conf_file)
        if have_system_conf or have_user_conf:
            if have_user_conf:
                configs.append(cparser.config_from_file(open(user_conf_file)))
            if have_system_conf:
                configs.append(
                    cparser.config_from_file(open(system_conf_file)))
        else:
            # make.conf...
            from pkgcore.ebuild.portage_conf import config_from_make_conf
            configs.append(config_from_make_conf())
    configs.extend(get_plugins('global_config'))
    return central.ConfigManager(configs, debug=debug)
