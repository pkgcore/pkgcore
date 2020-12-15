"""Collapse multiple config-sources and instantiate from them.

A lot of extra documentation on this is in dev-notes/config.rst.
"""

__all__ = ("CollapsedConfig", "ConfigManager",)

import weakref
from collections import defaultdict, deque, namedtuple
from itertools import chain

from snakeoil import klass, mappings
from snakeoil.compatibility import IGNORED_EXCEPTIONS

from . import basics, errors

_section_data = namedtuple('_section_data', ['name', 'section'])


class _ConfigMapping(mappings.DictMixin):

    """Minimal dict-like wrapper returning config sections by type.

    Similar to :class:`mappings.LazyValDict` but __getitem__
    does not call the key func for __getitem__.

    Careful: getting the keys for this mapping will collapse all of
    central's configs to get at their types, which might be slow if
    any of them are remote!
    """

    def __init__(self, manager, typename):
        super().__init__()
        self.manager = manager
        self.typename = typename

    def __getitem__(self, key):
        conf = self.manager.collapse_named_section(key, raise_on_missing=False)
        if conf is None or conf.type.name != self.typename:
            raise KeyError(key)
        return conf.instantiate()

    def keys(self):
        for name in self.manager.sections():
            try:
                collapsed = self.manager.collapse_named_section(name)
            except errors.ConfigError:
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


class _ConfigStack(defaultdict):

    def __init__(self):
        super().__init__(list)

    def render_vals(self, manager, key, type_name):
        for data in self.get(key, ()):
            if key in data.section:
                yield data.section.render_value(manager, key, type_name)

    def render_val(self, manager, key, type_name):
        for val in self.render_vals(manager, key, type_name):
            return val
        return None

    def render_prepends(self, manager, key, type_name, flatten=True):
        results = []
        # keep in mind that the sequence we get is a top -> bottom walk of the config
        # as such for this operation we have to reverse it when building the content-
        # specifically, reverse the ordering, but not the content of each item.
        data = []
        for content in self.render_vals(manager, key, type_name):
            data.append(content)
            if content[1]:
                break

        for prepend, this_content, append in reversed(data):
            if this_content:
                results = [this_content]
            if prepend:
                results = [prepend] + results
            if append:
                results += [append]

        if flatten:
            results = chain.from_iterable(results)
        return list(results)


class CollapsedConfig:

    """A collapsed config section.

    :type type: :obj:`basics.ConfigType`
    :ivar type: Our type.
    :type config: dict
    :ivar config: The supplied configuration values.
    :ivar debug: if True exception wrapping is disabled.
    :ivar default: True if this section is a default.
    :type name: C{str} or C{None}
    :ivar name: our section name or C{None} for an anonymous section.
    """

    def __init__(self, type_obj, config, manager, debug=False, default=False):
        """Initialize instance vars."""
        # Check if we got all values required to instantiate.
        missing = set(type_obj.required) - set(config)
        if missing:
            module = type_obj.callable.__module__
            name = type_obj.callable.__name__
            missing_vars = ', '.join(map(repr, missing))
            raise errors.ConfigurationError(
                f'type {module}.{name} needs settings for {missing_vars}')

        self.name = None
        self.default = default
        self.debug = debug
        self.type = type_obj
        self.config = config
        # Cached instance if we have one.
        self._instance = None
        if manager is not None:
            manager = weakref.ref(manager)
        self.manager = manager

    def instantiate(self):
        if self._instance is None:
            try:
                self._instance = self._instantiate()
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise errors.InstantiationError(self.name) from e
        return self._instance

    def _instantiate(self):
        """Call our type's callable, cache and return the result.

        Calling instantiate more than once will return the cached value.
        """

        # Needed because this code can run twice even with instance
        # caching if we trigger an ComplexInstantiationError.
        config = mappings.ProtectedDict(self.config)

        # Instantiate section refs.
        # Careful: not everything we have for needs to be in the conf dict
        # (because of default values) and not everything in the conf dict
        # needs to have a type (because of allow_unknowns).
        for name, val in config.items():
            typename = self.type.types.get(name)
            if typename is None:
                continue
            # central already checked the type, no need to repeat that here.
            unlist_it = False
            if typename.startswith('ref:'):
                val = [val]
                unlist_it = True
            if typename.startswith('refs:') or unlist_it:
                try:
                    final_val = []
                    for ref in val:
                        final_val.append(ref.instantiate())
                except IGNORED_EXCEPTIONS:
                    raise
                except Exception as e:
                    raise errors.ConfigurationError(
                        f'Instantiating reference {name!r} pointing at {ref.name!r}') from e
                if unlist_it:
                    final_val = final_val[0]
                config[name] = final_val


        if self.type.requires_config:
            if self.manager is None:
                raise Exception(
                    'configuration internal error; '
                    'requires_config is enabled '
                    'but we have no config manager to return '
                )
            manager = self.manager()
            if manager is None:
                raise Exception(
                    'Configuration internal error, potentially '
                    'client code error; manager requested, but the config '
                    'manager is no longer in memory'
                )

            config[self.type.requires_config] = manager

        callable_obj = self.type.callable
        # return raw, uninstantiated class object if requested
        if self.type.raw_class:
            return callable_obj

        pargs = []
        for var in self.type.positional:
            pargs.append(config.pop(var))
        # Python is basically the worst language ever:
        # TypeError: repo() argument after ** must be a dictionary
        configdict = dict(config)
        try:
            self._instance = callable_obj(*pargs, **configdict)
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            source = errors._identify_functor_source(self.type.callable)
            raise errors.InstantiationError(
                self.name, f'exception caught from {source!r}') from e
        if self._instance is None:
            raise errors.ComplexInstantiationError(
                'No object returned', callable_obj=callable_obj, pargs=pargs,
                kwargs=configdict)

        return self._instance

    def __getstate__(self):
        d = self.__dict__.copy()
        # pull actual value from weakref
        d['manager'] = d['manager']()
        return d

    def __setstate__(self, state):
        self.__dict__ = state.copy()
        # reset weakref
        self.__dict__['manager'] = weakref.ref(self.__dict__['manager'])


class _ConfigObjMap:

    def __init__(self, manager):
        self._manager = manager

    def __getattr__(self, attr):
        return _ConfigMapping(self._manager, attr)

    def __getitem__(self, key):
        val = getattr(self._manager.objects, key, klass.sentinel)
        if val is None:
            raise KeyError(key)
        return val

    def __getstate__(self):
        # Explicitly defined to force pickling to work as expected without
        # trying to pull __getstate__ from _ConfigMapping due to __getattr__.
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)


class CompatConfigManager:

    def __init__(self, manager):
        self._manager = manager

    def __getattr__(self, attr):
        if attr == '_manager':
            return object.__getattribute__(self, '_manager')
        obj = getattr(self._manager, attr, klass.sentinel)
        if obj is klass.sentinel:
            obj = getattr(self._manager.objects, attr)
        return obj

    __dir__ = klass.DirProxy("_manager")


class ConfigManager:

    """Combine config type definitions and configuration sections.

    Creates instances of a requested type and name by pulling the
    required data from any number of provided configuration sources.

    The following special type names are recognized:
      - configsection: instantiated and used the same way as an entry in the
        configs :obj:`__init__` arg.

    These "magic" typenames are only recognized if they are used by a
    section with a name starting with "autoload".
    """

    def __init__(self, configs=(), debug=False):
        """Initialize.

        :type configs: sequence of mappings of string to ConfigSection.
        :param configs: configuration to use.
            Can define extra configs that are also loaded.
        :param debug: if set to True exception wrapping is disabled.
            This means things can raise other exceptions than
            ConfigurationError but tracebacks are complete.
        """
        self.original_config_sources = tuple(map(self._compat_mangle_config, configs))
        # Set of encountered section names, used to catch recursive references.
        self._refs = set()
        self.debug = debug
        self.reload()
        # cycle...
        self.objects = _ConfigObjMap(self)

    def _compat_mangle_config(self, config):
        if hasattr(config, 'sections'):
            return config
        return basics.GeneratedConfigSource(config, "unknown")

    def reload(self):
        """Reinitialize us from the config sources originally passed in.

        This throws away all cached instances and re-executes autoloads.
        """
        # "Attribute defined outside __init__"
        # pylint: disable-msg=W0201
        self.configs = []
        self.config_sources = []
        # Cache mapping confname to CollapsedConfig.
        self.rendered_sections = {}
        self.sections_lookup = defaultdict(deque)
        # force regeneration.
        self._types = klass._uncached_singleton
        for config in self.original_config_sources:
            self.add_config_source(config)

    def add_config_source(self, config):
        return self._add_config_source(self._compat_mangle_config(config))

    def _add_config_source(self, config):
        """Pull extra type and config sections from configs and use them.

        Things loaded this way are added after already loaded things
        (meaning the config containing the autoload section overrides
        the config(s) added by that section).
        """
        config_data = config.sections()

        collision = set(self.rendered_sections)
        collision.intersection_update(config_data)

        if collision:
            # If this matches something we previously instantiated
            # we should probably blow up to prevent massive
            # amounts of confusion (and recursive autoloads)
            sections = ', '.join(repr(x) for x in sorted(collision))
            raise errors.ConfigurationError(
                'New config is trying to modify existing section(s) '
                f'{sections} that was already instantiated.'
            )

        self.configs.append(config_data)
        self.config_sources.append(config)
        for name in config_data:
            self.sections_lookup[name].appendleft(config_data[name])

            # Do not even touch the ConfigSection if it's not an autoload.
            if not name.startswith('autoload'):
                continue

            try:
                collapsed = self.collapse_named_section(name)
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise errors.ConfigurationError(
                    f'Failed collapsing autoload section {name!r}') from e

            if collapsed.type.name != 'configsection':
                raise errors.ConfigurationError(
                   f'Section {name!r} is marked as autoload but '
                   f'type is {collapsed.type.name}, not configsection'
                )
            try:
                instance = collapsed.instantiate()
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise errors.AutoloadInstantiationError(name) from e
            if collapsed.type.name == 'configsection':
                self.add_config_source(instance)

    def sections(self):
        """Return an iterator of all section names."""
        return iter(self.sections_lookup.keys())

    def collapse_named_section(self, name, raise_on_missing=True):
        """Collapse a config by name, possibly returning a cached instance.

        @returns: :obj:`CollapsedConfig`.

        If there is no section with this name a ConfigurationError is raised,
        unless raise_on_missing is False in which case None is returned.
        """
        if name in self._refs:
            raise errors.ConfigurationError(f'Reference to {name!r} is recursive')
        self._refs.add(name)
        try:
            result = self.rendered_sections.get(name)
            if result is not None:
                return result
            section_stack = self.sections_lookup.get(name)
            if section_stack is None:
                if not raise_on_missing:
                    return None
                raise errors.ConfigurationError(f'no section called {name!r}')
            try:
                result = self.collapse_section(section_stack, name)
                result.name = name
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise errors.ConfigurationError(
                    f'Collapsing section named {name!r}') from e
            self.rendered_sections[name] = result
            return result
        finally:
            self._refs.remove(name)

    def _get_inherited_sections(self, name, sections):
        # List of (name, ConfigSection, index) tuples, most specific first.
        slist = [(name, sections)]

        # first map out inherits.
        inherit_names = set([name])
        for current_section, section_stack in slist:
            current_conf = section_stack[0]
            if 'inherit' not in current_conf:
                continue
            prepend, inherits, append = current_conf.render_value(
                self, 'inherit', 'list')
            if prepend is not None or append is not None:
                raise errors.ConfigurationError(
                    'Prepending or appending to the inherit list makes no sense')
            for inherit in inherits:
                if inherit == current_section:
                    # self-inherit.  Mkae use of section_stack to handle this.
                    if len(section_stack) == 1:
                        # nothing else to self inherit.
                        raise errors.ConfigurationError(
                            f'Self-inherit {inherit!r} cannot be found')
                    if isinstance(section_stack, deque):
                        slist.append((inherit, list(section_stack)[1:]))
                    else:
                        slist.append((inherit, section_stack[1:]))
                else:
                    if inherit in inherit_names:
                        raise errors.ConfigurationError(
                            f'Inherit {inherit!r} is recursive')
                    inherit_names.add(inherit)
                    target = self.sections_lookup.get(inherit)
                    if target is None:
                        raise errors.ConfigurationError(
                            f'Inherit target {inherit!r} cannot be found')
                    slist.append((inherit, target))
        return [_section_data(name, stack[0]) for (name, stack) in slist]

    def _section_is_inherit_only(self, section):
        if 'inherit-only' in section:
            if section.render_value(self, 'inherit-only', 'bool'):
                return True
        return False

    def collapse_section(self, sections, _name=None):
        """Collapse a ConfigSection to a :obj:`CollapsedConfig`."""

        if self._section_is_inherit_only(sections[0]):
            if sections[0].render_value(self, 'inherit-only', 'bool'):
                raise errors.CollapseInheritOnly(
                    'cannot collapse inherit-only section')

        relevant_sections = self._get_inherited_sections(_name, sections)

        config_stack = _ConfigStack()
        for data in relevant_sections:
            for key in data.section.keys():
                config_stack[key].append(data)

        kls = config_stack.render_val(self, 'class', 'callable')
        if kls is None:
            raise errors.ConfigurationError('no class specified')
        type_obj = basics.ConfigType(kls)
        is_default = bool(config_stack.render_val(self, 'default', 'bool'))

        for key in ('inherit', 'inherit-only', 'class', 'default'):
            config_stack.pop(key, None)

        collapsed = CollapsedConfig(type_obj, self._render_config_stack(type_obj, config_stack),
            self, default=is_default, debug=self.debug)
        return collapsed

    @klass.jit_attr
    def types(self):
        type_map = defaultdict(dict)
        for name, sections in self.sections_lookup.items():
            if self._section_is_inherit_only(sections[0]):
                continue
            obj = self.collapse_named_section(name)
            type_map[obj.type.name][name] = obj
        return mappings.ImmutableDict(
            (k, mappings.ImmutableDict(v))
            for k,v in type_map.items())

    def _render_config_stack(self, type_obj, config_stack):
        conf = {}
        for key in config_stack:
            typename = type_obj.types.get(key)
            if typename is None:
                if not type_obj.allow_unknowns:
                    raise errors.ConfigurationError(f'Type of {key!r} unknown')
                typename = 'str'

            is_ref = typename.startswith('ref:')
            is_refs = typename.startswith('refs:')

            if typename.startswith('lazy_'):
                typename = typename[5:]

            if typename.startswith('refs:') or typename in ('list', 'str'):
                result = config_stack.render_prepends(self, key, typename, flatten=(typename != 'str'))
                if typename == 'str':
                    result = ' '.join(result)
            else:
                result = config_stack.render_val(self, key, typename)

            if is_ref:
                result = [result]
                is_refs = True

            if is_refs:
                try:
                    result = [ref.collapse() for ref in result]
                except IGNORED_EXCEPTIONS:
                    raise
                except Exception as e:
                    raise errors.ConfigurationError(
                        f'Failed collapsing section key {key!r}') from e
            if is_ref:
                result = result[0]

            conf[key] = result

        # Check if we got all values required to instantiate.
        missing = set(type_obj.required) - set(conf)
        if missing:
            module = type_obj.callable.__module__
            name = type_obj.callable.__name__
            missing_vars = ', '.join(map(repr, missing))
            raise errors.ConfigurationError(
                f'type {module}.{name} needs settings for {missing_vars}')

        return mappings.ImmutableDict(conf)

    def get_default(self, type_name):
        """Finds the configuration specified default obj of type_name.

        Returns C{None} if no defaults.
        """
        try:
            defaults = self.types.get(type_name, {}).items()
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            raise errors.ConfigurationError(
                f'Collapsing defaults for {type_name!r}') from e
        defaults = [(name, section) for name, section in defaults if section.default]

        if not defaults:
            return None

        if len(defaults) > 1:
            defaults = ', '.join(map(repr, sorted(x[0] for x in defaults)))
            raise errors.ConfigurationError(
                f'type {type_name} incorrectly has multiple default sections: {defaults}')

        try:
            return defaults[0][1].instantiate()
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            raise errors.ConfigurationError(
                f'failed instantiating default {type_name} {defaults[0][0]!r}') from e
        return None
