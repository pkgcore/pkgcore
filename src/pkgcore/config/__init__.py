"""configuration subsystem"""

__all__ = ('load_config',)

# keep these imports as minimal as possible; access to
# pkgcore.config isn't uncommon, thus don't trigger till
# actually needed

import os

from .. import const
from . import central, cparser


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
    if not skip_config_files:
        # load a pkgcore config file if one exists
        for config in (location, user_conf_file, system_conf_file):
            if config is not None and os.path.isfile(config):
                with open(config) as f:
                    configs.append(cparser.config_from_file(f))
                break
        # otherwise load the portage config
        else:
            # delay importing to avoid circular imports
            from pkgcore.ebuild.portage_conf import PortageConfig
            configs.append(PortageConfig(
                location=location, profile_override=profile_override, **kwargs))
    configs.extend(append_sources)
    return central.CompatConfigManager(central.ConfigManager(configs, debug=debug))
