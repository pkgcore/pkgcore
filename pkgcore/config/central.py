# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# Copyright: 2005-2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Collapse multiple config-sources and instantiate from them.

A lot of extra documentation on this is in dev-notes/config.rst.
"""

__all__ = ("CollapsedConfig", "ConfigManager",)

from pkgcore.config import errors, basics
from snakeoil import mappings


class _ConfigMapping(mappings.DictMixin):

    """Minimal dict-like wrapper returning config sections by type.

    Similar to L{LazyValDict<mappings.LazyValDict>} but __getitem__
    does not call the key func for __getitem__.

    Careful: getting the keys for this mapping will collapse all of
    central's configs to get at their types, which might be slow if
    any of them are remote!
    """

    def __init__(self, manager, typename):
        mappings.DictMixin.__init__(self)
        self.manager = manager
        self.typename = typename

    def __getitem__(self, key):
        conf = self.manager.collapse_named_section(key, raise_on_missing=False)
        if conf is None or conf.type.name != self.typename:
            raise KeyError(key)
        try:
            return conf.instantiate()
        except errors.ConfigurationError, e:
            e.stack.append('Instantiating named section %r' % (key,))
            raise

    def iterkeys(self):
        for config in self.manager.configs:
            for name in config:
                try:
                    collapsed = self.manager.collapse_named_section(name)
                except errors.BaseError:
                    # Cannot be collapsed, ignore it (this is not
                    # an error, it can be used as base for
                    # something that can be collapsed)
                    pass
                else:
                    if collapsed.type.name == self.typename:
                        yield name

    def __contains__(self, key):
        conf = self.manager.collapse_named_section(key, raise_on_missing=False)
        return conf is not None and conf.type.name == self.typename


class CollapsedConfig(object):

    """A collapsed config section.

    :type type: L{basics.ConfigType}
    @ivar type: Our type.
    :type config: dict
    @ivar config: The supplied configuration values.
    @ivar debug: if True exception wrapping is disabled.
    @ivar default: True if this section is a default.
    :type name: C{str} or C{None}
    @ivar name: our section name or C{None} for an anonymous section.
    """

    def __init__(self, type_obj, config, manager, debug=False, default=False):
        """Initialize instance vars."""
        # Check if we got all values required to instantiate.
        missing = set(type_obj.required) - set(config)
        if missing:
            raise errors.ConfigurationError(
                'type %s.%s needs settings for %s' % (
                    type_obj.callable.__module__,
                    type_obj.callable.__name__,
                    ', '.join(repr(var) for var in missing)))

        self.name = None
        self.default = default
        self.debug = debug
        self.type = type_obj
        self.config = config
        # Cached instance if we have one.
        self._instance = None

    def instantiate(self):
        """Call our type's callable, cache and return the result.

        Calling instantiate more than once will return the cached value.
        """
        if self._instance is not None:
            return self._instance

        # Needed because this code can run twice even with instance
        # caching if we trigger an InstantiationError.
        config = mappings.ProtectedDict(self.config)

        # Instantiate section refs.
        # Careful: not everything we have for needs to be in the conf dict
        # (because of default values) and not everything in the conf dict
        # needs to have a type (because of allow_unknowns).
        for name, val in config.iteritems():
            typename = self.type.types.get(name)
            if typename is None:
                continue
            # central already checked the type, no need to repeat that here.
            if typename.startswith('ref:'):
                try:
                    config[name] = val.instantiate()
                except errors.ConfigurationError, e:
                    e.stack.append('Instantiating ref %r' % (name,))
                    raise
            elif typename.startswith('refs:'):
                try:
                    config[name] = list(ref.instantiate() for ref in val)
                except errors.ConfigurationError, e:
                    e.stack.append('Instantiating refs %r' % (name,))
                    raise

        callable_obj = self.type.callable

        pargs = []
        for var in self.type.positional:
            pargs.append(config.pop(var))
        # Python is basically the worst language ever:
        # TypeError: repo() argument after ** must be a dictionary
        configdict = dict(config)
        try:
            self._instance = callable_obj(*pargs, **configdict)
        except errors.InstantiationError, e:
            # This is probably just paranoia, but better safe than sorry.
            if e.callable is None:
                e.callable = callable_obj
                e.pargs = pargs
                e.kwargs = configdict
            raise
        except (RuntimeError, SystemExit, KeyboardInterrupt):
            raise
        except Exception, e:
            if self.debug:
                raise
            raise errors.InstantiationError(exception=e,
                                            callable_obj=callable_obj,
                                            pargs=pargs, kwargs=configdict)
        if self._instance is None:
            raise errors.InstantiationError(
                'No object returned', callable_obj=callable_obj, pargs=pargs,
                kwargs=configdict)

        return self._instance


class ConfigManager(object):

    """Combine config type definitions and configuration sections.

    Creates instances of a requested type and name by pulling the
    required data from any number of provided configuration sources.

    The following special type names are recognized:
      - configsection: instantiated and used the same way as an entry in the
        configs L{__init__} arg.
      - remoteconfigsection: Instantiated and used the same way as an entry in
        theremote_configs L{__init__} arg.

    These "magic" typenames are only recognized if they are used by a
    section with a name starting with "autoload".
    """

    def __init__(self, configs=(), remote_configs=(), debug=False):
        """Initialize.

        :type configs: sequence of mappings of string to ConfigSection.
        :param configs: configuration to use.
            Can define extra configs that are also loaded.
        :type remote_configs: sequence of mappings of string to ConfigSection.
        :param remote_configs: configuration to use.
            Cannot define extra configs.
        :param debug: if set to True exception wrapping is disabled.
            This means things can raise other exceptions than
            ConfigurationError but tracebacks are complete.
        """
        self.original_configs = tuple(configs)
        self.original_remote_configs = tuple(remote_configs)
        # Set of encountered section names, used to catch recursive references.
        self._refs = set()
        self.debug = debug
        self.reload()

    def reload(self):
        """Reinitialize us from the config sources originally passed in.

        This throws away all cached instances and re-executes autoloads.
        """
        # "Attribute defined outside __init__"
        # pylint: disable-msg=W0201
        self.configs = (list(self.original_configs) +
                        list(self.original_remote_configs))
        # Cache mapping confname to CollapsedConfig.
        self.collapsed_configs = {}
        self._exec_configs(self.original_configs)

    def __getattr__(self, attr):
        return _ConfigMapping(self, attr)

    def _exec_configs(self, configs):
        """Pull extra type and config sections from configs and use them.

        Things loaded this way are added after already loaded things
        (meaning the config containing the autoload section overrides
        the config(s) added by that section).
        """
        new_configs = []
        for config in configs:
            for name in config:
                # Do not even touch the ConfigSection if it's not an autoload.
                if not name.startswith('autoload'):
                    continue
                # If this matches something we previously instantiated
                # we should probably blow up to prevent massive
                # amounts of confusion (and recursive autoloads)
                if name in self.collapsed_configs:
                    raise errors.ConfigurationError(
                        'section %r from autoload is already collapsed!' % (
                            name,))
                try:
                    collapsed = self.collapse_named_section(name)
                except errors.ConfigurationError, e:
                    e.stack.append('Collapsing autoload %r' % (name,))
                    raise
                if collapsed.type.name not in (
                    'configsection', 'remoteconfigsection'):
                    raise errors.ConfigurationError(
                        'Section %r is marked as autoload but type is %s, not '
                        '(remote)configsection' % (name, collapsed.type.name))
                try:
                    instance = collapsed.instantiate()
                except errors.ConfigurationError, e:
                    e.stack.append('Instantiating autoload %r' % (name,))
                    raise
                if collapsed.type.name == 'configsection':
                    new_configs.append(instance)
                elif collapsed.type.name == 'remoteconfigsection':
                    self.configs.append(instance)
        if new_configs:
            self.configs.extend(new_configs)
            self._exec_configs(new_configs)

    def sections(self):
        """Return an iterator of all section names."""
        for config in self.configs:
            for name in config:
                yield name

    def collapse_named_section(self, name, raise_on_missing=True):
        """Collapse a config by name, possibly returning a cached instance.

        @returns: L{CollapsedConfig}.

        If there is no section with this name a ConfigurationError is raised,
        unless raise_on_missing is False in which case None is returned.
        """
        if name in self._refs:
            raise errors.ConfigurationError(
                'Reference to %r is recursive' % (name,))
        self._refs.add(name)
        try:
            result = self.collapsed_configs.get(name)
            if result is not None:
                return result
            for source_index, config in enumerate(self.configs):
                if name in config:
                    section = config[name]
                    break
            else:
                if raise_on_missing:
                    if name == "portdir":
                        # gentoo-related usability --jokey
                        raise errors.ConfigurationError(
                            "no section called %r, maybe you didn't add autoload-portage to your file" % (name,))
                    else:
                        raise errors.ConfigurationError(
                            'no section called %r' % (name,))
                return None
            try:
                result = self.collapse_section(section, name, source_index)
                result.name = name
            except errors.ConfigurationError, e:
                e.stack.append('Collapsing section named %r' % (name,))
                raise
            self.collapsed_configs[name] = result
            return result
        finally:
            self._refs.remove(name)

    def collapse_section(self, section, _name=None, _index=None):
        """Collapse a ConfigSection to a L{CollapsedConfig}."""

        # Bail if this is an inherit-only (uncollapsable) section.
        try:
            inherit_only = section.get_value(self, 'inherit-only', 'bool')
        except (AttributeError, KeyError):
            pass
        else:
            if inherit_only:
                raise errors.CollapseInheritOnly(
                    'cannot collapse inherit-only section')

        # List of (name, ConfigSection, index) tuples, most specific first.
        slist = [(_name, section, _index)]

        # first map out inherits.
        inherit_names = set([_name])
        for current_section, current_conf, index in slist:
            if 'inherit' not in current_conf:
                continue
            prepend, inherits, append = current_conf.get_value(
                self, 'inherit', 'list')
            if prepend is not None or append is not None:
                raise errors.ConfigurationError(
                    'Prepending or appending to the inherit list makes no '
                    'sense')
            for inherit in inherits:
                if inherit == current_section:
                    # Self-inherit is a bit special.
                    for i, config in enumerate(self.configs[index + 1:]):
                        if inherit in config:
                            slist.append((inherit, config[inherit],
                                          index + i + 1))
                            break
                    else:
                        raise errors.ConfigurationError(
                            'Self-inherit %r cannot be found' % (inherit,))
                else:
                    if inherit in inherit_names:
                        raise errors.ConfigurationError(
                            'Inherit %r is recursive' % (inherit,))
                    inherit_names.add(inherit)
                    for i, config in enumerate(self.configs):
                        if inherit in config:
                            slist.append((inherit, config[inherit], i))
                            break
                    else:
                        raise errors.ConfigurationError(
                            'inherit target %r cannot be found' % (inherit,))

        # Grab the "class" setting first (we need it to get a type obj
        # to collapse to the right type in the more general loop)
        for inherit_name, inherit_conf, index in slist:
            if "class" in inherit_conf:
                break
        else:
            raise errors.ConfigurationError('no class specified')

        type_obj = basics.ConfigType(inherit_conf.get_value(self, 'class',
                                                            'callable'))

        conf = {}
        for section_nr, (inherit_name, inherit_conf, index) in \
                enumerate(reversed(slist)):
            for key in inherit_conf.keys():
                if key in ('class', 'inherit', 'inherit-only'):
                    continue
                typename = type_obj.types.get(key)
                if typename is None:
                    if key == 'default':
                        typename = 'bool'
                    elif not type_obj.allow_unknowns:
                        if section_nr != len(slist) - 1:
                            raise errors.ConfigurationError(
                                'Type of %r inherited from %r unknown' % (
                                    key, inherit_name))
                        raise errors.ConfigurationError(
                            'Type of %r unknown' % (key,))
                    else:
                        typename = 'str'
                is_ref = typename.startswith('ref:')
                is_refs = typename.startswith('refs:')
                # The sections do not care about lazy vs nonlazy.
                if typename.startswith('lazy_'):
                    typename = typename[5:]
                result = inherit_conf.get_value(self, key, typename)
                if is_ref:
                    try:
                        result = result.collapse()
                    except errors.ConfigurationError, e:
                        e.stack.append(
                            'Collapsing section ref %r' % (key,))
                        raise
                elif is_refs:
                    try:
                        result = list(
                            list(ref.collapse() for ref in subresult or ())
                            for subresult in result)
                    except errors.ConfigurationError, e:
                        e.stack.append(
                            'Collapsing section refs %r' % (key,))
                        raise
                if typename == 'list' or typename.startswith('refs:'):
                    prepend, result, append = result
                    if result is None:
                        if key in conf:
                            result = conf[key]
                        else:
                            result = []
                    if prepend:
                        result = prepend + result
                    if append:
                        result += append
                elif typename == 'str':
                    prepend, result, append = result
                    if result is None and key in conf:
                        result = conf[key]
                    result = ' '.join(
                        v for v in (prepend, result, append) if v)
                conf[key] = result
        default = conf.pop('default', False)
        return CollapsedConfig(
            type_obj, conf, self, debug=self.debug, default=default)

    def get_default(self, type_name):
        """Finds the configuration specified default obj of type_name.

        Returns C{None} if no defaults.
        """
        # The name of the "winning" default or None if there is none.
        default_name = None
        # The collapsed default section or None.
        default = None
        for source in self.configs:
            for name, section in source.iteritems():
                collapsed = None
                try:
                    is_default = section.get_value(self, 'default', 'bool')
                except KeyError:
                    is_default = False
                if not is_default:
                    continue
                # We need to know the type name of this section, for
                # which we need the class. Try to grab this from the
                # section directly:
                try:
                    klass = section.get_value(self, 'class', 'callable')
                except errors.ConfigurationError:
                    # There is a class setting but it is not valid.
                    # This means it is definitely not the one we are
                    # interested in, so just skip this.
                    continue
                except KeyError:
                    # There is no class value on the section. Collapse
                    # it to see if it inherits one:
                    try:
                        collapsed = self.collapse_named_section(name)
                    except errors.ConfigurationError:
                        # Uncollapsable. Just ignore this, since we
                        # have no clean way of determining if this
                        # would be an "interesting" section if it
                        # could be collapsed (and complaining about
                        # every uncollapsable section with
                        # default=true would be too much).
                        continue
                    type_obj = collapsed.type
                else:
                    # Grabbed the class directly from the section.
                    type_obj = basics.ConfigType(klass)
                if type_obj.name != type_name:
                    continue
                if default_name is not None:
                    raise errors.ConfigurationError(
                        'both %r and %r are default for %r' % (
                            default_name, name, type_name))
                default_name = name
                default = collapsed
            if default_name is not None:
                if default is None:
                    try:
                        default = self.collapse_named_section(default_name)
                    except errors.ConfigurationError, e:
                        e.stack.append('Collapsing default %s %r' % (
                                type_name, default_name))
                        raise
                try:
                    return default.instantiate()
                except errors.ConfigurationError, e:
                    e.stack.append('Instantiating default %s %r' %
                                   (type_name, default_name))
                    raise
        return None
