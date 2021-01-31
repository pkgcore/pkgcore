================
 Plugins system
================

Goals
=====

The plugin system (``pkgcore.plugin``) is used to pick up extra code
(potentially distributed separately from pkgcore itself) at a place
where using the config system is not a good idea for some reason. This
means that for a lot of things that most people would call "plugins"
you should not actually use ``pkgcore.plugin``, you should use the
config system. Things like extra repository types should simply be
used as "class" value in the configuration. The plugin system is
currently mainly used in places where handing in a ``ConfigManager``
is too inconvenient.

Using plugins
=============

Plugins are looked up based on a string "key". You can always look up
all available plugins matching this key with
``pkgcore.plugin.get_plugins(key)``. For some kinds of plugin (the
ones defining a "priority" attribute) you can also get the "best"
plugin with ``pkgcore.plugin.get_plugin(key)``. This does not make
sense for all kinds of plugin, so not all of them define this.

The plugin system does not care about what kind of object plugins are,
this depends entirely on the key.

Adding plugins
==============

Basics, caching
---------------

Plugins for pkgcore are loaded from modules inside the
``pkgcore.plugins`` package. This package has some magic to make
plugins in any subdirectory ``pkgcore/plugins`` under a directory on
``sys.path`` work. So if pkgcore itself is installed in site-packages
you can still add plugins to ``/home/you/pythonlib/pkgcore/plugins``
if ``/home/you/pythonlib`` is in ``PYTHONPATH``. You should not put an
``__init__.py`` in this extra plugin directory.

Plugin modules should contain a ``pkgcore_plugins`` directory that
maps the "key" strings to a sequence of plugins. This dictionary has
to be constant, since pkgcore keeps track of what plugin module
provides plugins for what keys in a cache file to avoid unnecessary
imports. So this is invalid::

 try:
     import spork_package
 except ImportError:
     pkgcore_plugins = {}
 else:
     pkgcore_plugins = {'myplug': [spork_package.ThePlugin]}

since if the plugin cache is generated while the package is not
available pkgcore will cache the module as not providing any
``myplug`` plugins, and the cache will not be updated if the package
becomes available (only changes to the mtime of actual plugin modules
invalidate the cache). Instead you should do something like this::

 try:
     from spork_package import ThePlugin
 except ImportError:
     class ThePlugin:
         disabled = True

 pkgcore_plugins = {'myplug': [ThePlugin]}

If a plugin has a "disabled" attribute the plugin system will never
return it from ``get_plugin`` or ``get_plugins``.

Priority
--------

If you want your plugin to support ``get_plugin`` it should have a
``priority`` attribute: an integer indicating how "preferred" this
plugin is. The plugin with the highest priority (that is not disabled)
is returned from ``get_plugin``.

Some types of plugins need more information to determine a priority
value. Those should not have a priority attribute. They should use
``get_plugins`` instead and have a method that gets passed the extra
data and returns the priority.

Import behaviour
----------------

Assuming the cache is working correctly (it was generated after
installing a plugin as root) pkgcore will import all plugin modules
containing plugins for a requested key in priority order until it hits
one that is not disabled. The "disabled" value is not cached (a plugin
that is unconditionally disabled makes no sense), but the priority
value is. You can fake a dynamic priority by having two instances of
your plugin registered and only one of them enabled at the same
time.

This means it makes sense to have only one kind of plugin per plugin
module (unless the required imports overlap): this avoids pulling in
imports for other kinds of plugin when one kind of plugin is
requested.

The disabled value is not cached by the plugin system after the plugin
module is imported. This means it should be a simple attribute (either
completely constant or set at import time) or property that does its
own caching.

Adding a plugin package
=======================

Both ``get_plugin`` and ``get_plugins`` take a plugin package as
second argument. This means you can use the plugin system for external
pkgcore-related tools without cluttering up the main pkgcore plugin
directory. If you do this you will probably want to copy the
``__path__`` trick from ``pkgcore/plugin/__init__.py`` to support
plugins elsewhere on ``sys.path``.
