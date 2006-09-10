# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
per key file based backend
"""

import os, stat, errno
from pkgcore.cache import fs_template
from pkgcore.cache import cache_errors

class database(fs_template.FsBased):

    """
    stores cache entries in key=value form, stripping newlines
    """
    autocommits = True

    def __init__(self, *args, **config):
        super(database, self).__init__(*args, **config)
        self.location = os.path.join(self.location,
            self.label.lstrip(os.path.sep).rstrip(os.path.sep))

        if not os.path.exists(self.location):
            self._ensure_dirs()
    __init__.__doc__ = fs_template.FsBased.__init__.__doc__

    def _getitem(self, cpv):
        try:
            myf = open(os.path.join(self.location, cpv), "r", 32384)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise KeyError(cpv)
            raise cache_errors.CacheCorruption(cpv, e)
        except OSError, e:
            raise cache_errors.CacheCorruption(cpv, e)
        try:
            d = self._parse_data(myf, os.fstat(myf.fileno()).st_mtime)
        except (OSError, ValueError), e:
            myf.close()
            raise cache_errors.CacheCorruption(cpv, e)
        myf.close()
        return d

    def _parse_data(self, data, mtime):
        splitter = (x.rstrip().split("=", 1) for x in data)
        d = self._cdict_kls((k,v) for k,v in splitter if k in self._known_keys)
        d["_mtime_"] = long(mtime)
        return d

    def _setitem(self, cpv, values):
        s = cpv.rfind("/")
        fp = os.path.join(self.location,
                          cpv[:s], ".update.%i.%s" % (os.getpid(), cpv[s+1:]))
        try:
            myf = open(fp, "w", 32384)
        except IOError, ie:
            if ie.errno == errno.ENOENT:
                try:
                    self._ensure_dirs(cpv)
                    myf = open(fp, "w", 32384)
                except (OSError, IOError),e:
                    raise cache_errors.CacheCorruption(cpv, e)
            else:
                raise cache_errors.CacheCorruption(cpv, ie)
        except OSError, e:
            raise cache_errors.CacheCorruption(cpv, e)

        for k, v in values.iteritems():
            if k != "_mtime_":
                myf.writelines("%s=%s\n" % (k, v))

        myf.close()
        self._ensure_access(fp, mtime=values["_mtime_"])

        #update written.  now we move it.

        new_fp = os.path.join(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except (OSError, IOError), e:
            os.remove(fp)
            raise cache_errors.CacheCorruption(cpv, e)

    def _delitem(self, cpv):
        try:
            os.remove(os.path.join(self.location, cpv))
        except OSError, e:
            if e.errno == errno.ENOENT:
                raise KeyError(cpv)
            else:
                raise cache_errors.CacheCorruption(cpv, e)

    def __contains__(self, cpv):
        return os.path.exists(os.path.join(self.location, cpv))

    def iterkeys(self):
        """generator for walking the dir struct"""
        dirs = [self.location]
        len_base = len(self.location)
        while dirs:
            d = dirs.pop(0)
            for l in os.listdir(d):
                if l.endswith(".cpickle"):
                    continue
                p = os.path.join(d, l)
                st = os.lstat(p)
                if stat.S_ISDIR(st.st_mode):
                    dirs.append(p)
                    continue
                yield p[len_base+1:]
