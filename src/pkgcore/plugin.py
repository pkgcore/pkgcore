"""Plugin system, heavily inspired by twisted's plugin system."""

__all__ = ("initialize_cache", "get_plugins", "get_plugin")

# Implementation note: we have to be pretty careful about error
# handling in here since some core functionality in pkgcore uses this
# code. Since we can function without a cache we will generally be
# noisy but keep working if something is wrong with the cache.
#
# Currently we explode if something is wrong with a plugin package
# dir, but not if something prevents importing a module in it.
# Rationale is the former should be a PYTHONPATH issue while the
# latter an installed plugin issue. May have to change this if it
# causes problems.

import operator
import os.path
import sys
from collections import defaultdict, namedtuple
from importlib import import_module

from snakeoil import mappings, modules
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.fileutils import AtomicWriteFile, readlines_ascii
from snakeoil.osutils import (ensure_dirs, listdir_files, pjoin,
                              unlink_if_exists)

from . import const, os_data
from .log import logger

_plugin_data = namedtuple(
    "_plugin_data", ["key", "priority", "source", "target"])

PLUGIN_ATTR = 'pkgcore_plugins'

CACHE_HEADER = 'pkgcore plugin cache v3'
CACHE_FILENAME = 'plugincache'


def _clean_old_caches(path):
    for name in ('plugincache2',):
        try:
            unlink_if_exists(pjoin(path, name))
        except EnvironmentError as e:
            logger.error(
                "attempting to clean old plugin cache %r failed with %s",
                pjoin(path, name), e)


def sort_plugs(plugs):
    return sorted(plugs, reverse=True, key=lambda x: (x.key, x.priority, x.source))


def _process_plugins(package, sequence, filter_disabled=False):
    for plug in sequence:
        plug = _process_plugin(package, plug, filter_disabled)
        if plug is not None:
            yield plug


def _process_plugin(package, plug, filter_disabled=False):
    if isinstance(plug.target, str):
        plug = modules.load_any(plug.target)
    elif isinstance(plug.target, int):
        module = modules.load_any(plug.source)
        plugs = getattr(module, PLUGIN_ATTR, {})
        plugs = plugs.get(plug.key, [])
        if len(plugs) <= plug.target:
            logger.exception(
                "plugin cache for %s, %s, %s is somehow wrong; no item at position %s",
                package.__name__, plug.source, plug.key, plug.target)
            return None
        plug = plugs[plug.target]
    else:
        logger.error(
            "package %s, plug %s; non int, non string.  wtf?",
            package.__name__, plug)
        return None

    if filter_disabled:
        if getattr(plug, 'disabled', False):
            logger.debug("plugin %s is disabled, skipping", plug)
            return None
        f = getattr(plug, '_plugin_disabled_check', None)
        if f is not None and f():
            logger.debug("plugin %s is disabled, skipping", plug)
            return None

    return plug

def _read_cache_file(package, cache_path):
    """Read an existing cache file."""
    stored_cache = {}
    cache_data = list(readlines_ascii(cache_path, True, True, False))
    if len(cache_data) >= 1:
        if cache_data[0] != CACHE_HEADER:
            logger.warning(
                "plugin cache has a wrong header: %r, regenerating", cache_data[0])
            cache_data = []
        else:
            cache_data = cache_data[1:]
    if not cache_data:
        return {}
    try:
        for line in cache_data:
            module, mtime, entries = line.split(':', 2)
            mtime = int(mtime)
            # Needed because ''.split(':') == [''], not []
            if not entries:
                entries = set()
            else:
                entries = entries.replace(':', ',').split(',')

                if not len(entries) % 3 == 0:
                    logger.error(
                        "failed reading cache %s; entries field isn't "
                        "divisable by 3: %r", cache_path, entries)
                    continue
                entries = iter(entries)
                def f(val):
                    if val.isdigit():
                        val = int(val)
                    return val
                entries = set(
                    _plugin_data(
                        key, int(priority),
                        f'{package.__name__}.{module}', f(target))
                    for (key, priority, target) in zip(entries, entries, entries))
            stored_cache[(module, mtime)] = entries
    except IGNORED_EXCEPTIONS:
        raise
    except Exception as e:
        logger.warning("failed reading cache; exception %s, regenerating.", e)
        stored_cache.clear()

    return stored_cache

def _write_cache_file(path, data, uid=-1, gid=-1):
    """Write a new cache file."""
    cachefile = None
    try:
        try:
            cachefile = AtomicWriteFile(
                path, binary=False, perms=0o664, uid=uid, gid=gid)
            cachefile.write(CACHE_HEADER + "\n")
            for (module, mtime), plugs in sorted(data.items(), key=operator.itemgetter(0)):
                plugs = sort_plugs(plugs)
                plugs = ':'.join(f'{plug.key},{plug.priority},{plug.target}' for plug in plugs)
                cachefile.write(f'{module}:{mtime}:{plugs}\n')
            cachefile.close()
        except EnvironmentError as e:
            # We cannot write a new cache. We should log this
            # since it will have a performance impact.

            # Use error, not exception for this one: the traceback
            # is not necessary and too alarming.
            logger.error('Cannot write cache for %s: %s. '
                         'Try running pplugincache.',
                         path, e)
    finally:
        if cachefile is not None:
            cachefile.discard()


def initialize_cache(package, force=False, cache_dir=None):
    """Determine available plugins in a package.

    Writes cache files if they are stale and writing is possible.
    """
    modpath = os.path.dirname(package.__file__)
    pkgpath = os.path.dirname(os.path.dirname(modpath))
    uid = gid = -1
    mode = 0o755

    if cache_dir is None:
        if not force:
            # use user-generated caches if they exist, fallback to module cache
            if os.path.exists(pjoin(const.USER_CACHE_PATH, CACHE_FILENAME)):
                cache_dir = const.USER_CACHE_PATH
            elif os.path.exists(pjoin(const.SYSTEM_CACHE_PATH, CACHE_FILENAME)):
                cache_dir = const.SYSTEM_CACHE_PATH
                uid = os_data.portage_uid
                gid = os_data.portage_gid
                mode = 0o775
            else:
                cache_dir = modpath
        else:
            # generate module cache when running from git repo, otherwise create system/user cache
            if pkgpath == sys.path[0]:
                cache_dir = modpath
            elif os_data.uid in (os_data.root_uid, os_data.portage_uid):
                cache_dir = const.SYSTEM_CACHE_PATH
                uid = os_data.portage_uid
                gid = os_data.portage_gid
                mode = 0o775
            else:
                cache_dir = const.USER_CACHE_PATH

    # put pkgcore consumer plugins (e.g. pkgcheck) inside pkgcore cache dir
    if cache_dir in (const.SYSTEM_CACHE_PATH, const.USER_CACHE_PATH):
        chunks = package.__name__.split('.', 1)
        if chunks[0] != os.path.basename(cache_dir):
            cache_dir = pjoin(cache_dir, chunks[0])

    # package plugin cache, see above.
    package_cache = defaultdict(set)
    stored_cache_name = pjoin(cache_dir, CACHE_FILENAME)
    stored_cache = _read_cache_file(package, stored_cache_name)

    if force:
        _clean_old_caches(cache_dir)

    # Directory cache, mapping modulename to
    # (mtime, set([keys]))
    modlist = listdir_files(modpath)
    modlist = set(x for x in modlist if os.path.splitext(x)[1] == '.py'
                  and x != '__init__.py')

    cache_stale = False
    # Hunt for modules.
    actual_cache = defaultdict(set)
    mtime_cache = mappings.defaultdictkey(lambda x: int(os.path.getmtime(x)))
    for modfullname in sorted(modlist):
        modname = os.path.splitext(modfullname)[0]
        # It is an actual module. Check if its cache entry is valid.
        mtime = mtime_cache[pjoin(modpath, modfullname)]
        vals = stored_cache.get((modname, mtime))
        if vals is None or force:
            # Cache entry is stale.
            logger.debug(
                'stale because of %s: actual %s != stored %s',
                modname, mtime, stored_cache.get(modname, (0, ()))[0])
            cache_stale = True
            entries = []
            qualname = '.'.join((package.__name__, modname))
            module = import_module(qualname)
            registry = getattr(module, PLUGIN_ATTR, {})
            vals = set()
            for key, plugs in registry.items():
                for idx, plug_name in enumerate(plugs):
                    if isinstance(plug_name, str):
                        plug = _process_plugin(package, _plugin_data(key, 0, qualname, plug_name))
                    else:
                        plug = plug_name
                    if plug is None:
                        # import failure, ignore it, error already logged
                        continue
                    priority = getattr(plug, 'priority', 0)
                    if not isinstance(priority, int):
                        logger.error(
                            "ignoring plugin %s: has a non integer priority: %s",
                            plug, priority)
                        continue
                    if plug_name is plug:
                        # this means it's an object, rather than a string; store
                        # the offset.
                        plug_name = idx
                    data = _plugin_data(key, priority, qualname, plug_name)
                    vals.add(data)
        actual_cache[(modname, mtime)] = vals
        for data in vals:
            package_cache[data.key].add(data)
    if force or set(stored_cache) != set(actual_cache):
        logger.debug('updating cache %r for new plugins', stored_cache_name)
        ensure_dirs(cache_dir, uid=uid, gid=gid, mode=mode)
        _write_cache_file(stored_cache_name, actual_cache, uid=uid, gid=gid)

    return mappings.ImmutableDict((k, sort_plugs(v)) for k, v in package_cache.items())


def get_plugins(key, package=None):
    """Return all enabled plugins matching "key".

    Plugins with a C{disabled} attribute evaluating to C{True} are skipped.
    """
    if package is None:
        package = import_module('.plugins', __name__.split('.')[0])

    cache = _global_cache[package]
    for plug in _process_plugins(package, cache.get(key, ()), filter_disabled=True):
        yield plug


def get_plugin(key, package=None):
    """Get a single plugin matching this key.

    This assumes all plugins for this key have a priority attribute.
    If any of them do not the AttributeError is not stopped.

    :return: highest-priority plugin or None if no plugin available.
    """
    if package is None:
        package = import_module('.plugins', __name__.split('.')[0])

    cache = _global_cache[package]
    for plug in _process_plugins(package, cache.get(key, ()), filter_disabled=True):
        # first returned will be the highest.
        return plug
    return None


def extend_path(path, name):
    """Simpler version of the stdlib's :obj:`pkgutil.extend_path`.

    It does not support ".pkg" files, and it does not require an
    __init__.py (this is important: we want only one thing (pkgcore
    itself) to install the __init__.py to avoid name clashes).

    It also modifies the "path" list in place (and returns C{None})
    instead of copying it and returning the modified copy.
    """
    if not isinstance(path, list):
        # This could happen e.g. when this is called from inside a
        # frozen package.  Return the path unchanged in that case.
        return
    # Reconstitute as relative path.
    pname = pjoin(*name.split('.'))

    for entry in sys.path:
        if not isinstance(entry, str) or not os.path.isdir(entry):
            continue
        subdir = pjoin(entry, pname)
        # XXX This may still add duplicate entries to path on
        # case-insensitive filesystems
        if subdir not in path:
            path.append(subdir)


# Global plugin cache. Mapping of package to package cache, which is a
# mapping of plugin key to a list of module names.
_global_cache = mappings.defaultdictkey(initialize_cache)
