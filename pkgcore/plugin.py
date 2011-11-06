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
from snakeoil.compatibility import cmp, sort_cmp
from snakeoil import modules, demandload
demandload.demandload(globals(), 'tempfile', 'errno', 'pkgcore.log:logger')


CACHE_HEADER = 'pkgcore plugin cache v2\n'

# Global plugin cache. Mapping of package to package cache, which is a
# mapping of plugin key to a list of module names.
_cache = {}


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
        stored_cache = {}
        stored_cache_name = pjoin(path, 'plugincache2')
        try:
            cachefile = open(stored_cache_name)
        except IOError:
            # Something is wrong with the cache file. We just handle
            # this as a missing/empty cache, which will force a
            # rewrite. If whatever it is that is wrong prevents us
            # from writing the new cache we log it there.
            pass
        else:
            try:
                # Remove this extra nesting once we require python 2.5
                try:
                    if cachefile.readline() != CACHE_HEADER:
                        raise ValueError('bogus header')
                    for line in cachefile:
                        module, mtime, entries = line[:-1].split(':', 2)
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
                except ValueError:
                    # Corrupt cache, treat as empty.
                    stored_cache = {}
            finally:
                cachefile.close()
        cache_stale = False
        # Hunt for modules.
        actual_cache = {}
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
            mtime = int(os.path.getmtime(pjoin(path, modfullname)))
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
                    logger.exception('plugin import failed')
                else:
                    values = set()
                    registry = getattr(module, 'pkgcore_plugins', {})
                    for key, plugs in registry.iteritems():
                        max_prio = None
                        for plug in plugs:
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
        for key in stored_cache:
            if key not in actual_cache and key not in assumed_valid:
                logger.debug('stale because %s is no longer there', key)
                cache_stale = True
                break
        if cache_stale:
            # Write a new cache.
            try:
                fd, name = tempfile.mkstemp(dir=path)
            except OSError, e:
                # We cannot write a new cache. We should log this
                # since it will have a performance impact.

                # Use error, not exception for this one: the traceback
                # is not necessary and too alarming.
                logger.error('Cannot write cache for %s: %s. '
                             'Try running pplugincache.',
                             stored_cache_name, e)
            else:
                cachefile = os.fdopen(fd, 'w')
                cachefile.write(CACHE_HEADER)
                try:
                    for module, (mtime, entries) in actual_cache.iteritems():
                        strings = []
                        for plugname, max_prio in entries:
                            if max_prio is None:
                                strings.append(plugname + ',')
                            else:
                                strings.append('%s,%s' % (plugname, max_prio))
                        cachefile.write(
                            '%s:%s:%s\n' % (module, mtime, ':'.join(strings)))
                finally:
                    cachefile.close()
                os.chmod(name, 0644)
                os.rename(name, stored_cache_name)
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
    cache = _cache.get(package)
    if cache is None:
        cache = _cache[package] = initialize_cache(package)
    for modname, max_prio in cache.get(key, ()):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for obj in module.pkgcore_plugins.get(key, ()):
            if getattr(obj, 'disabled', False):
               continue
            f = getattr(obj, '_plugin_disabled_check', None)
            if f is not None and f():
                continue
            yield obj


def get_plugin(key, package=plugins):
    """Get a single plugin matching this key.

    This assumes all plugins for this key have a priority attribute.
    If any of them do not the AttributeError is not stopped.

    :return: highest-priority plugin or None if no plugin available.
    """
    cache = _cache.get(package)
    if cache is None:
        cache = _cache[package] = initialize_cache(package)
    modlist = cache.get(key, [])
    # explicitly force cmp.  for py3k, our compatibility cmp
    # still allows None comparisons.
    sort_cmp(modlist, cmp, key=operator.itemgetter(1), reverse=True)
    plugs = []
    for i, (modname, max_prio) in enumerate(modlist):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for plug in module.pkgcore_plugins.get(key, ()):
            # sanity check.
            if getattr(plug, 'disabled', False):
                logger.debug("pluging %s is disabled, skipping" % plug)
            elif plug.priority is None:
                logger.warn("plugin %s has an invalid priority, skipping" % plug)
            else:
                plugs.append(plug)
        if not plugs:
            continue
        plugs.sort(key=operator.attrgetter('priority'), reverse=True)
        if i + 1 == len(modlist) or plugs[0].priority > modlist[i + 1][1]:
            return plugs[0]
    return None
