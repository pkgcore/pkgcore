"""Helpers for testing scripts."""

from snakeoil.cli import arghparse
from snakeoil.test import argparse_helpers

from ...config import basics, central
from ...config.hint import ConfigHint


class fake_domain:
    pkgcore_config_type = ConfigHint(typename='domain')

    def __init__(self):
        pass

default_domain = basics.HardCodedConfigSection({
    'class': fake_domain,
    'default': True,
    })


class ArgParseMixin(argparse_helpers.ArgParseMixin):
    """Provide some utility methods for testing the parser and main.

    :cvar parser: ArgumentParser subclass to test.
    :cvar main: main function to test.
    """

    requires_compat_config_manager = True
    suppress_domain = False
    has_config = True

    def _mk_config(self, *args, **kwds):
        config = central.ConfigManager(*args, **kwds)
        if self.requires_compat_config_manager:
            config = central.CompatConfigManager(config)
        return config

    def parse(self, *args, **kwargs):
        """Parse a commandline and return the Values object.

        args are passed to parse_args, keyword args are used as config keys.
        """
        ns_kwargs = kwargs.pop('ns_kwargs', {})
        namespace = kwargs.get('namespace', arghparse.Namespace(**ns_kwargs))
        if self.has_config:
            if kwargs.pop("suppress_domain", self.suppress_domain):
                kwargs["default_domain"] = default_domain
            namespace.config = self._mk_config([kwargs], debug=True)
        namespace = self.parser.parse_args(list(args), namespace=namespace)
        return namespace

    def assertOutAndErr(self, *args, **kwargs):
        options = argparse_helpers.ArgParseMixin.assertOutAndErr(self, *args, **kwargs)
        return options.config
