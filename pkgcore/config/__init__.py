# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""
configuration subsystem
"""

__all__ = ("ConfigHint", "configurable", "load_config")

# keep these imports as minimal as possible; access to
# pkgcore.config isn't uncommon, thus don't trigger till
# actually needed
from pkgcore.const import SYSTEM_CONF_FILE, USER_CONF_FILE

_config = None

class ConfigHint(object):

    """hint for introspection supplying overrides"""

    # be aware this is used in clone
    __slots__ = (
        "types", "positional", "required", "typename", "allow_unknowns",
        "doc", "authorative", 'requires_config')

    def __init__(self, types=None, positional=None, required=None, doc=None,
                 typename=None, allow_unknowns=False, authorative=False,
                 requires_config=False):
        self.types = types or {}
        self.positional = positional or []
        self.required = required or []
        self.typename = typename
        self.allow_unknowns = allow_unknowns
        self.doc = doc
        self.authorative = authorative
        self.requires_config = requires_config

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
                debug=False, prepend_sources=(), append_sources=(),
                skip_config_files=False, profile_override=None):
    """
    the main entry point for any code looking to use pkgcore.

    :param user_conf_file: file to attempt to load, else defaults to trying to
        load portage 2 style configs (/etc/portage/make.conf and
        /etc/portage/make.profile or the deprecated /etc/make.conf and
        /etc/make.profile locations)
    :param profile_override: profile to use instead of the current system
        profile, i.e. the target path of the /etc/portage/make.profile
        (or deprecated /etc/make.profile) symlink

    :return: :obj:`pkgcore.config.central.ConfigManager` instance
        representing the system config.
    """

    global _config

    # True if load_config is called with no arguments or the passed arguments match the defaults
    cached = user_conf_file == USER_CONF_FILE and system_conf_file == SYSTEM_CONF_FILE and \
        not any((debug, prepend_sources, append_sources, skip_config_files, profile_override))

    if _config is None or not cached:
        from pkgcore.config import central, cparser
        from pkgcore.plugin import get_plugins
        import os

        configs = list(prepend_sources)
        configs.extend(get_plugins('global_config'))
        if not skip_config_files:
            have_system_conf = os.path.isfile(system_conf_file)
            have_user_conf = os.path.isfile(user_conf_file)
            if have_system_conf or have_user_conf:
                if have_system_conf:
                    with open(system_conf_file) as f:
                        configs.append(cparser.config_from_file(f))
                if have_user_conf:
                    with open(user_conf_file) as f:
                        configs.append(cparser.config_from_file(f))
            else:
                # make.conf...
                from pkgcore.ebuild.portage_conf import config_from_make_conf
                configs.append(config_from_make_conf(profile_override=profile_override))
        configs.extend(append_sources)
        _config = central.CompatConfigManager(central.ConfigManager(configs, debug=debug))
    return _config
