# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


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

from pkgcore import plugins
from snakeoil.osutils import join as pjoin, listdir_files
from snakeoil import compatibility
from snakeoil import modules, demandload, mappings, sequences
demandload.demandload(globals(),
    'tempfile',
    'errno',
    'pkgcore.log:logger',
    'snakeoil:fileutils',
)

_plugin_data = sequences.namedtuple("_plugin_data",
    ["key", "priority", "source", "target"])

PLUGIN_ATTR = 'pkgcore_plugins'

CACHE_HEADER = 'pkgcore plugin cache v3'
CACHE_FILENAME = 'plugincache'

def sort_plugs(plugs):
    return sorted(plugs, reverse=True, key=lambda x:(x.key, x.priority, x.source))

def _process_plugins(package, sequence, filter_disabled=False):
    for plug in sequence:
        plug = _process_plugin(package, plug, filter_disabled)
        if plug is not None:
            yield plug

def _process_plugin(package, plug, filter_disabled=False):
    if isinstance(plug.target, basestring):
        try:
            plug = modules.load_any(plug.target)
        except modules.FailedImport, e:
            logger.exception("plugin import for %s failed processing file %s, entry %s: %s",
                package.__name__, plug.source, plug.target, e)
            return None
    elif isinstance(plug.target, int):
        try:
            module = modules.load_any(plug.source)
        except modules.FailedImport, e:
            logger.exception("plugin import for %s failed processing file %s: %s",
                package.__name__, plug.source, e)
            return None
        plugs = getattr(module, PLUGIN_ATTR, {})
        plugs = plugs.get(plug.key, [])
        if len(plugs) <= plug.target:
            logger.exception("plugin cache for %s, %s, %s is somehow wrong; no item at position %s",
                package.__name__, plug.source, plug.key, plug.target)
            return None
        plug = plugs[plug.target]
    else:
        logger.error("package %s, plug %s; non int, non string.  wtf?",
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
    stored_cache = {}
    cache_data = list(fileutils.readlines_ascii(cache_path, True, True, False))
    if len(cache_data) >= 1:
        if cache_data[0] != CACHE_HEADER:
            logger.warn("plugin cache has a wrong header: %r, regenerating",
                cache_data[0])
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
                    logger.error("failed reading cache %s; entries field isn't "
                        "divisable by 3: %r", cache_path, entries)
                    continue
                entries = iter(entries)
                def f(val):
                    if val.isdigit():
                        val = int(val)
                    return val
                entries = set(
                    _plugin_data(key, int(priority), '%s.%s' % (package.__name__, module),
                        f(target))
                        for (key, priority, target) in zip(entries, entries, entries))
            stored_cache[(module,mtime)] = entries

    except compatibility.IGNORED_EXCEPTIONS:
        raise
    except Exception, e:
      logger.warn("failed reading cache; exception %s.  Regenerating.", e)
      stored_cache.clear()

    return stored_cache

def _write_cache_file(path, data):
    # Write a new cache.
    cachefile = None
    try:
        try:
            cachefile = fileutils.AtomicWriteFile(path, binary=False, perms=0664)
            cachefile.write(CACHE_HEADER + "\n")
            for (module, mtime), plugs in sorted(data.iteritems(), key=operator.itemgetter(0)):
                plugs = sort_plugs(plugs)
                plugs = ':'.join('%s,%s,%s' % (plug.key, plug.priority, plug.target) for plug in plugs)
                cachefile.write("%s:%s:%s\n" % (module, mtime, plugs))
            cachefile.close()
        except EnvironmentError, e:
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


def initialize_cache(package):
    """Determine available plugins in a package.

    Writes cache files if they are stale and writing is possible.
    """
    # package plugin cache, see above.
    package_cache = mappings.defaultdict(set)
    seen_modnames = set()
    for path in package.__path__:
        # Check if the path actually exists first.
        try:
            modlist = listdir_files(path)
        except OSError, e:
            if e.errno not in (errno.ENOENT, errno.ENOTDIR):
                raise
            continue
        # Directory cache, mapping modulename to
        # (mtime, set([keys]))
        modlist = set(x for x in modlist if os.path.splitext(x)[1] == '.py'
                and x != '__init__.py')
        modlist.difference_update(seen_modnames)

        stored_cache_name = pjoin(path, CACHE_FILENAME)
        stored_cache = _read_cache_file(package, stored_cache_name)
        cache_stale = False
        # Hunt for modules.
        actual_cache = mappings.defaultdict(set)
        mtime_cache = mappings.defaultdictkey(lambda x:int(os.path.getmtime(x)))
        for modfullname in sorted(modlist):
            modname = os.path.splitext(modfullname)[0]
            # It is an actual module. Check if its cache entry is valid.
            mtime = mtime_cache[pjoin(path, modfullname)]
            vals = stored_cache.get((modname, mtime))
            if vals is None:
                # Cache entry is stale.
                logger.debug(
                    'stale because of %s: actual %s != stored %s',
                    modname, mtime, stored_cache.get(modname, (0, ()))[0])
                cache_stale = True
                entries = []
                qualname = '.'.join((package.__name__, modname))
                try:
                    module = modules.load_module(qualname)
                except modules.FailedImport:
                    # This is a serious problem, but if we blow up
                    # here we cripple pkgcore entirely which may make
                    # fixing the problem impossible. So be noisy but
                    # try to continue.
                    logger.exception('plugin import failed for %s processing %s',
                        package.__name__, modname)
                    continue

                registry = getattr(module, PLUGIN_ATTR, {})
                vals = set()
                for key, plugs in registry.iteritems():
                    for idx, plug_name in enumerate(plugs):
                        if isinstance(plug_name, basestring):
                            plug = _process_plugin(package, _plugin_data(key, 0, qualname, plug_name))
                        else:
                            plug = plug_name
                        if plug is None:
                            # import failure, ignore it, error already logged
                            continue
                        priority = getattr(plug, 'priority', 0)
                        if not isinstance(priority, int):
                            logger.error("ignoring plugin %s: has a non integer priority: %s",
                                plug, priority)
                            continue
                        if plug_name is plug:
                            # this means it's an object, rather than a string; store
                            # the offset.
                            plug_name = idx
                        data = _plugin_data(key, priority, qualname, plug_name)
                        vals.add(data)
            actual_cache[(modname,mtime)] = vals
            seen_modnames.add(modfullname)
            for data in vals:
                package_cache[data.key].add(data)
        if set(stored_cache) != set(actual_cache):
            logger.debug('updating cache %r for new plugins', stored_cache_name)
            _write_cache_file(stored_cache_name, actual_cache)

    return mappings.ImmutableDict((k, sort_plugs(v)) for k,v in package_cache.iteritems())


def get_plugins(key, package=plugins):
    """Return all enabled plugins matching "key".

    Plugins with a C{disabled} attribute evaluating to C{True} are skipped.
    """
    cache = _global_cache[package]
    for plug in _process_plugins(package, cache.get(key, ()), filter_disabled=True):
        yield plug


def get_plugin(key, package=plugins):
    """Get a single plugin matching this key.

    This assumes all plugins for this key have a priority attribute.
    If any of them do not the AttributeError is not stopped.

    :return: highest-priority plugin or None if no plugin available.
    """
    cache = _global_cache[package]
    for plug in _process_plugins(package, cache.get(key, ()), filter_disabled=True):
        # first returned will be the highest.
        return plug
    return None

# Global plugin cache. Mapping of package to package cache, which is a
# mapping of plugin key to a list of module names.
_global_cache = mappings.defaultdictkey(initialize_cache)

