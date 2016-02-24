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

from snakeoil.demandload import demandload

from pkgcore import const

demandload(
    'os',
    'pkgcore.config:central,cparser',
    'pkgcore.ebuild.portage_conf:config_from_make_conf',
    'pkgcore.log:logger',
    'pkgcore.plugin:get_plugins',
)


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


def load_config(user_conf_file=const.USER_CONF_FILE,
                system_conf_file=const.SYSTEM_CONF_FILE,
                debug=False, prepend_sources=(), append_sources=(),
                skip_config_files=False, profile_override=None,
                location=None, **kwargs):
    """The main entry point for any code looking to use pkgcore.

    Args:
        user_conf_file (optional[str]): pkgcore user config file path
        system_conf_file (optional[str]): system pkgcore config file path
        profile_override (optional[str]): targeted profile instead of system setting
        location (optional[str]): path to pkgcore config file or portage config directory
        skip_config_files (optional[str]): don't attempt to load any config files

    Returns:
        :obj:`pkgcore.config.central.ConfigManager` instance: system config
    """
    configs = list(prepend_sources)
    configs.extend(get_plugins('global_config'))
    if not skip_config_files:
        # load a pkgcore config file if one exists
        for config in (location,
                       user_conf_file, const.OLD_USER_CONF_FILE,
                       system_conf_file, const.OLD_SYSTEM_CONF_FILE):
            if config is not None and os.path.isfile(config):
                # TODO: drop the deprecation notice for 0.10
                if config in (const.OLD_USER_CONF_FILE, const.OLD_SYSTEM_CONF_FILE):
                    logger.warning(
                        'The config file location %s is deprecated, please move '
                        'the file to %s for user configs or %s for system configs.',
                        config, const.USER_CONF_FILE, const.SYSTEM_CONF_FILE)
                with open(config) as f:
                    configs.append(cparser.config_from_file(f))
                break
        # otherwise load the portage config
        else:
            configs.append(config_from_make_conf(
                location=location, profile_override=profile_override, **kwargs))
    configs.extend(append_sources)
    return central.CompatConfigManager(central.ConfigManager(configs, debug=debug))
