# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""New plugin system. Not in its final location yet.

This is heavily inspired by twisted's plugin system.
"""

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

import errno
import tempfile
import operator
import os.path

from pkgcore import plugins
from pkgcore.util import modules, demandload
demandload.demandload(globals(), 'logging')


# Global plugin cache. Mapping of package to package cache, which is a
# mapping of plugin key to a list of module names.
_cache = {}


def initialize_cache(package):
    """Determine available plugins in a package.

    Writes cache files if they are stale and writing is possible.
    """
    # package plugin cache, see above.
    package_cache = {}
    for path in package.__path__:
        # Check if the path actually exists first.
        try:
            modlist = os.listdir(path)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise
            continue
        # Directory cache, mapping modulename to
        # (mtime, set([keys]))
        stored_cache = {}
        stored_cache_name = os.path.join(path, 'plugincache')
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
                    for line in cachefile:
                        module, mtime, entries = line[:-1].split(':', 2)
                        mtime = int(mtime)
                        entries = set(entries.split(':'))
                        stored_cache[module] = (mtime, entries)
                except ValueError:
                    # Corrupt cache, treat as empty.
                    cachefile = {}
            finally:
                cachefile.close()
        cache_stale = False
        # Hunt for modules.
        actual_cache = {}
        for modfullname in modlist:
            modname, modext = os.path.splitext(modfullname)
            if modext not in ('.pyc', '.pyo', '.py'):
                continue
            if modname == '__init__':
                continue
            # It is an actual module. Check if its cache entry is valid.
            mtime = int(os.path.getmtime(os.path.join(path, modfullname)))
            if mtime == stored_cache.get(modname, (0, ()))[0]:
                # Cache is good, use it.
                actual_cache[modname] = stored_cache[modname]
            else:
                # Cache entry is stale.
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
                    logging.exception('plugin import failed')
                else:
                    keys = set(getattr(module, 'pkgcore_plugins', {}))
                    actual_cache[modname] = (mtime, keys)
        # Cache is also stale if it sees entries that are no longer there.
        for key in stored_cache:
            if key not in actual_cache:
                cache_stale = True
                break
        if cache_stale:
            # Write a new cache.
            try:
                fd, name = tempfile.mkstemp(dir=path)
            except OSError, e:
                # We cannot write a new cache. We should log this
                # since it will have a performance impact.

                # Use logging.error, not logging.exception for this
                # one: the traceback is not necessary and too alarming.
                logging.error('Cannot write cache for %s: %s. '
                              'Try running pplugincache.',
                              stored_cache_name, e)
            else:
                cachefile = os.fdopen(fd, 'w')
                for module, (mtime, entries) in actual_cache.iteritems():
                    cachefile.write(
                        '%s:%s:%s\n' % (module, mtime, ':'.join(entries)))
                cachefile.close()
                os.chmod(name, 0644)
                os.rename(name, stored_cache_name)
        # Update the package_cache.
        for module, (mtime, entries) in actual_cache.iteritems():
            for key in entries:
                package_cache.setdefault(key, []).append(module)
    return package_cache


def get_plugins(key, package=plugins):
    """Return all enabled plugins matching "key".

    Plugins with a C{disabled} attribute evaluating to C{True} are skipped.
    """
    cache = _cache.get(package)
    if cache is None:
        cache = _cache[package] = initialize_cache(package)
    for modname in cache.get(key, ()):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for obj in module.pkgcore_plugins.get(key, ()):
            if not getattr(obj, 'disabled', False):
                yield obj


def get_plugin(key, package=plugins):
    """Get a single plugin matching this key.

    This assumes all plugins for this key have a priority attribute.
    If any of them do not the AttributeError is not stopped.

    @return: highest-priority plugin or None if no plugin available.
    """
    candidates = list(plugin for plugin in get_plugins(key, package))
    if not candidates:
        return None
    candidates.sort(key=operator.attrgetter('priority'))
    return candidates[-1]
