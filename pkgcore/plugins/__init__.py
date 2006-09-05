# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
global plugin registry- may be nuked/deprecated in the near future

functionality it provides the config subsystem should be able to provide
"""

# I don't like this.
# doesn't seem clean/right.

import os
from pkgcore.const import plugins_dir
from pkgcore.fs.util import FsLock, ensure_dirs, NonExistant
from pkgcore.os_data import portage_gid, root_uid
from ConfigParser import RawConfigParser
from pkgcore.util.modules import load_attribute


PLUGINS_EXTENSION = ".plugins"

class RegistrationException(Exception):
    def __init__(self, reason):
        Exception.__init__(self, "failed action due to %s" % (reason,))
        self.reason = reason

class FailedDir(RegistrationException):
    pass

class PluginExistsAlready(RegistrationException):
    def __init__(self):
        RegistrationException.__init__(
            self, "plugin exists aleady, magic found")

class FailedUpdating(RegistrationException):
    def __str__(self):
        return "failed updating plugin_type due error: %s" % (self.reason)

class PluginNotFound(RegistrationException):
    def __init__(self, plugin, reason="unknown"):
        RegistrationException.__init__(self, "plugin %s not found" % (plugin,))
        self.plugin, self.reason = plugin, reason
    def __str__(self):
        return "Plugin '%s' wasn't found; reason: %s" % (
            self.plugin, self.reason)


class GlobalPluginRegistry(object):
    def register(self, plugin_type, magic, version, namespace, replace=False):
        """register a plugin
        plugin_type is a string, the category of the plugin
        magic is a string, magic constant of the plugin
        version is the specific plugin version (only one can be installed at a time)
        namespace is the pythonic namespace for that plugin
        replace controls whether or not a plugin_type + magic conflict will be replaced, or error out"""
        if not ensure_dirs(plugins_dir, uid=root_uid, gid=portage_gid,
                           mode=0755):
            raise FailedDir("Failed ensuring base plugins dir")

        # this could be fine grained down to per plugin_type
        plug_lock = FsLock(plugins_dir)
        plug_lock.acquire_write_lock()
        try:
            ptype_fp = os.path.join(plugins_dir,
                                    plugin_type.lstrip(os.path.sep)
                                    + PLUGINS_EXTENSION)
            existing = self.query_plugins(plugin_type, locking=False, raw=True)
            if existing.has_section(magic):
                if not replace:
                    raise PluginExistsAlready()
                existing.remove_section(magic)
            existing.add_section(magic)
            existing.set(magic, "version", version)
            existing.set(magic, "namespace", namespace)
            try:
                f = open(ptype_fp, "w")
                os.chmod(ptype_fp, 0644)
                os.chown(ptype_fp, root_uid, portage_gid)
                existing.write(f)
                f.close()
            except OSError, oe:
                raise FailedUpdating(oe)

        finally:
            plug_lock.release_write_lock()

    def deregister(self, plugin_type, magic, version, ignore_errors=False):
        """plugin_type is the categorization of the plugin
        magic is the magic constant for lookup
        version is the version of the plugin to yank
        ignore_errors controls whether or not an exception is thrown when the plugin isn't found"""
        plug_lock = FsLock(plugins_dir)
        plug_lock.acquire_write_lock()
        try:
            ptype_fp = os.path.join(plugins_dir,
                                    plugin_type.lstrip(os.path.sep) +
                                    PLUGINS_EXTENSION)
            existing = self.query_plugins(locking=False, raw=True)
            if plugin_type not in existing:
                if ignore_errors:
                    return
                raise PluginNotFound(magic, "no plugin type")

            existing = existing[plugin_type]
            if not existing.has_section(magic):
                if ignore_errors:
                    return
                raise PluginNotFound(magic, "magic not found in plugin_type")

            if (not existing.has_option(magic, "version") or
                str(version) != existing.get(magic, "version")):
                if ignore_errors:
                    return
                raise PluginNotFound(magic, "version not found in plugin_type")

            existing.remove_section(magic)
            try:
                if not existing.sections():
                    os.unlink(ptype_fp)
                else:
                    f = open(ptype_fp, "w")
                    os.chmod(ptype_fp, 0644)
                    os.chown(ptype_fp, root_uid, portage_gid)
                    existing.write(f)
                    f.close()
            except OSError, oe:
                raise FailedUpdating(oe)

        finally:
            plug_lock.release_write_lock()

    def get_plugin(self, plugin_type, magic):
        try:
            address = self.query_plugins(plugin_type)[magic]["namespace"]
        except KeyError:
            raise PluginNotFound(magic)
        return load_attribute(address)

    def query_plugins(self, plugin_type=None, locking=True, raw=False):
        # designed this way to minimize lock holding time.
        if plugin_type is not None:
            ptypes = [plugin_type + PLUGINS_EXTENSION]
        d = {}
        if locking:
            try:
                plug_lock = FsLock(plugins_dir)
            except NonExistant:
                return {}
            plug_lock.acquire_read_lock()
        try:
            if plugin_type is None:
                ptypes = [x for x in os.listdir(plugins_dir)
                          if x.endswith(PLUGINS_EXTENSION)]

            len_exten = len(PLUGINS_EXTENSION)
            for x in ptypes:
                c = RawConfigParser()
                c.read(os.path.join(plugins_dir, x.lstrip(os.path.sep)))
                if raw:
                    d[x[:-len_exten]] = c
                else:
                    d[x[:-len_exten]] = dict((y, dict(c.items(y)))
                                             for y in c.sections())

        finally:
            if locking:
                plug_lock.release_read_lock()
        if plugin_type is not None:
            return d[plugin_type]
        return d


registry = None
from pkgcore.util.currying import pre_curry, pretty_docs

def proxy_it(method, *a, **kw):
    global registry
    if registry is None:
        registry = GlobalPluginRegistry()
    return getattr(registry, method)(*a, **kw)

for x in ["register", "deregister", "query_plugins", "get_plugin"]:
    v = pre_curry(proxy_it, x)
    doc = getattr(GlobalPluginRegistry, x).__doc__
    if doc is None:
        doc = ''
    else:
        # do this so indentation on pydoc __doc__ is sane
        doc = "\n".join(x.lstrip() for x in doc.split("\n")) +"\n"
    doc += "proxied call to module level registry instances %s method" % x
    globals()[x] = pretty_docs(v, doc)

del x, v, proxy_it, doc
