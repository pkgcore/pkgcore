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
from snakeoil import modules, demandload, mappings
demandload.demandload(globals(),
    'tempfile',
    'errno',
    'pkgcore.log:logger',
    'snakeoil:fileutils',
)


CACHE_HEADER = 'pkgcore plugin cache v2'
CACHE_FILENAME = 'plugincache2'

def _process_plugins(package, modname, sequence, filter_disabled=False):
    for plug in sequence:
        if isinstance(plug, basestring):
            try:
                plug = modules.load_any(plug)
            except modules.FailedImport, e:
                logger.exception("plugin import for %s failed processing file %s, entry %s: %s",
                    package.__name__, modname, plug, e)
                continue
        if filter_disabled:
            if getattr(plug, 'disabled', False):
                logger.debug("plugin %s is disabled, skipping", plug)
                continue
            f = getattr(plug, '_plugin_disabled_check', None)
            if f is not None and f():
                logger.debug("plugin %s is disabled, skipping", plug)
                continue

        yield plug

def _read_cache_file(cache_path):
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
            result = set()
            # Needed because ''.split(':') == [''], not []
            if entries:
                for s in entries.split(':'):
                    name, max_prio = s.split(',')
                    if max_prio:
                        max_prio = int(max_prio)
                    else:
                        max_prio = None
                    result.add((name, max_prio))
            stored_cache[module] = (mtime, result)

    except compatibility.IGNORED_EXCEPTIONS:
        raise
    except Exception, e:
        # corrupt cache, or bug in this code.
        logger.warn("failed reading cache; exception %s.  Regenerating.",
            e)
        return {}
    return stored_cache

def _write_cache_file(path, data):
    # Write a new cache.
    cachefile = None
    try:
        try:
            cachefile = fileutils.AtomicWriteFile(path, binary=False, perms=0664)
            cachefile.write(CACHE_HEADER + "\n")
            for module, (mtime, entries) in data.iteritems():
                strings = []
                for plugname, max_prio in entries:
                    if max_prio is None:
                        strings.append(plugname + ',')
                    else:
                        strings.append('%s,%s' % (plugname, max_prio))
                cachefile.write('%s:%s:%s\n' % (module, mtime, ':'.join(strings)))
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
    package_cache = {}
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
        stored_cache_name = pjoin(path, CACHE_FILENAME)
        stored_cache = _read_cache_file(stored_cache_name)
        cache_stale = False
        # Hunt for modules.
        actual_cache = {}
        mtime_cache = mappings.defaultdictkey(lambda x:int(os.path.getmtime(x)))
        assumed_valid = set()
        for modfullname in modlist:
            modname, modext = os.path.splitext(modfullname)
            if modext != '.py':
                continue
            if modname == '__init__':
                continue
            if modname in seen_modnames:
                # This module is shadowed by a module earlier in
                # sys.path. Skip it, assuming its cache is valid.
                assumed_valid.add(modname)
                continue
            # It is an actual module. Check if its cache entry is valid.
            mtime = mtime_cache[pjoin(path, modfullname)]
            if mtime == stored_cache.get(modname, (0, ()))[0]:
                # Cache is good, use it.
                actual_cache[modname] = stored_cache[modname]
            else:
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
                values = set()
                registry = getattr(module, 'pkgcore_plugins', {})
                for key, plugs in registry.iteritems():
                    max_prio = None
                    for plug in _process_plugins(package, modname, plugs):
                        priority = getattr(plug, 'priority', None)
                        if priority is not None \
                                and not isinstance(priority, int):
                            # This happens rather a lot with
                            # plugins not meant for use with
                            # get_plugin. Just ignore it.
                            priority = None
                        if priority is not None and (
                            max_prio is None or priority > max_prio):
                            max_prio = priority
                    values.add((key, max_prio))
                actual_cache[modname] = (mtime, values)
        # Cache is also stale if it sees entries that are no longer there.
        stale = set(stored_cache)
        stale.difference_update(actual_cache)
        stale.difference_update(assumed_valid)
        if stale:
            logger.debug('stale due to %r no longer existing', sorted(stale))
            cache_stale = True
        if cache_stale:
            _write_cache_file(stored_cache_name, actual_cache)

        # Update the package_cache.
        for module, (mtime, entries) in actual_cache.iteritems():
            seen_modnames.add(module)
            for key, max_prio in entries:
                package_cache.setdefault(key, []).append((module, max_prio))
    return package_cache


def get_plugins(key, package=plugins):
    """Return all enabled plugins matching "key".

    Plugins with a C{disabled} attribute evaluating to C{True} are skipped.
    """
    cache = _cache[package]
    for modname, max_prio in cache.get(key, ()):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for obj in _process_plugins(package, modname, module.pkgcore_plugins.get(key, ()),
            filter_disabled=True):
            yield obj


def get_plugin(key, package=plugins):
    """Get a single plugin matching this key.

    This assumes all plugins for this key have a priority attribute.
    If any of them do not the AttributeError is not stopped.

    :return: highest-priority plugin or None if no plugin available.
    """
    cache = _cache[package]
    modlist = cache.get(key, [])
    # explicitly force cmp.  for py3k, our compatibility cmp
    # still allows None comparisons.
    compatibility.sort_cmp(modlist, compatibility.cmp,
        key=operator.itemgetter(1), reverse=True)
    plugs = []

    for i, (modname, max_prio) in enumerate(modlist):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for plug in _process_plugins(package, modname, module.pkgcore_plugins.get(key, ()),
            filter_disabled=True):
            if plug.priority is None:
                logger.warn("plugin %s has an invalid priority, skipping" % plug)
            else:
                plugs.append(plug)
        if not plugs:
            continue
        plugs.sort(key=operator.attrgetter('priority'), reverse=True)
        if i + 1 == len(modlist) or plugs[0].priority > modlist[i + 1][1]:
            return plugs[0]
    return None

# Global plugin cache. Mapping of package to package cache, which is a
# mapping of plugin key to a list of module names.
_cache = mappings.defaultdictkey(initialize_cache)

