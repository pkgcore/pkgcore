# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""New plugin system. Not in its final location yet.

This is heavily inspired by twisted's plugin system.
"""

import errno
import tempfile
import operator
import os.path

from pkgcore import plugins2
from pkgcore.util import modules


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
        # Directory cache, mapping modulename to
        # (mtime, set([keys]))
        stored_cache = {}
        # TODO more errorhandling.
        try:
            cachefile = open(os.path.join(path, 'plugincache'))
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            # No cache, ignore this.
        else:
            try:
                entries = None
                for line in cachefile:
                    module, mtime, entries = line[:-1].split(':', 2)
                    mtime = int(mtime)
                    entries = set(entries.split(':'))
                    stored_cache[module] = (mtime, entries)
            finally:
                cachefile.close()
        cache_stale = False
        # Hunt for modules.
        actual_cache = {}
        try:
            modlist = os.listdir(path)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise
            continue
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
                module = modules.load_module(qualname)
                keys = set(getattr(module, 'pkgcore_plugins', {}))
                actual_cache[modname] = (mtime, keys)
        # Cache is also stale if it sees entries that are no longer there.
        if cache_stale or set(actual_cache) != set(stored_cache):
            # Write a new cache.
            fd, name = tempfile.mkstemp(dir=path)
            cachefile = os.fdopen(fd, 'w')
            for module, (mtime, entries) in actual_cache.iteritems():
                cachefile.write(
                    '%s:%s:%s\n' % (module, mtime, ':'.join(entries)))
            cachefile.close()
            os.rename(name, os.path.join(path, 'plugincache'))
        # Update the package_cache.
        for module, (mtime, entries) in actual_cache.iteritems():
            for key in entries:
                package_cache.setdefault(key, []).append(module)
    return package_cache


def get_plugins(key, package=plugins2):
    """Return all enabled plugins matching "key".

    Plugins with a C{disabled} attribute evaluating to C{True} are skipped.
    """
    cache = _cache.get(package)
    if cache is None:
        cache = _cache[package] = initialize_cache(package)
    for modname in cache.get(key, ()):
        module = modules.load_module('.'.join((package.__name__, modname)))
        for obj, call in module.pkgcore_plugins.get(key, ()):
            if call:
                obj = obj()
            if not getattr(obj, 'disabled', False):
                yield obj


def get_plugin(key, package=plugins2):
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
