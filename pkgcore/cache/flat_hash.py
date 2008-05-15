# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
per key file based backend
"""

import os, stat, errno
from pkgcore.cache import fs_template
from pkgcore.cache import errors
from pkgcore.config import ConfigHint
from snakeoil.osutils import join as pjoin, readlines

class database(fs_template.FsBased):

    """
    stores cache entries in key=value form, stripping newlines
    """

    # TODO different way of passing in default auxdbkeys and location
    pkgcore_config_type = ConfigHint(
        {'readonly': 'bool', 'location': 'str', 'label': 'str',
         'auxdbkeys': 'list'},
        required=['location'],
        positional=['location'],
        typename='cache')


    autocommits = True

    def _getitem(self, cpv):
        path = pjoin(self.location, cpv)
        try:
            data = readlines(path, True, True, True)
        except (IOError, OSError), e:
            raise errors.CacheCorruption(cpv, e)
        if data is None:
            raise KeyError(cpv)
        try:
            d = self._parse_data(data, data.mtime)
        except (OSError, ValueError), e:
            raise errors.CacheCorruption(cpv, e)
        return d

    def _parse_data(self, data, mtime):
        d = self._cdict_kls()
        known = self._known_keys
        for x in data:
            k, v = x.split("=", 1)
            if k in known:
                d[k] = v

        if self._mtime_used:
            d["_mtime_"] = long(mtime)
        return d

    def _setitem(self, cpv, values):
        # might seem weird, but we rely on the trailing +1; this
        # makes it behave properly for any cache depth (including no depth)
        s = cpv.rfind("/") + 1
        fp = pjoin(self.location,
            cpv[:s], ".update.%i.%s" % (os.getpid(), cpv[s:]))
        try:
            myf = open(fp, "w", 32768)
        except IOError, ie:
            if ie.errno == errno.ENOENT:
                if not self._ensure_dirs(cpv):
                    raise errors.CacheCorruption(
                        cpv, 'error creating directory for %r' % (fp,))
                try:
                    myf = open(fp, "w", 32768)
                except (OSError, IOError), e:
                    raise errors.CacheCorruption(cpv, e)
            else:
                raise errors.CacheCorruption(cpv, ie)
        except OSError, e:
            raise errors.CacheCorruption(cpv, e)

        for k, v in values.iteritems():
            if k != "_mtime_":
                myf.writelines("%s=%s\n" % (k, v))

        myf.close()
        if self._mtime_used:
            self._ensure_access(fp, mtime=values["_mtime_"])
        else:
            self._ensure_access(fp)

        #update written.  now we move it.

        new_fp = pjoin(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except (OSError, IOError), e:
            os.remove(fp)
            raise errors.CacheCorruption(cpv, e)

    def _delitem(self, cpv):
        try:
            os.remove(pjoin(self.location, cpv))
        except OSError, e:
            if e.errno == errno.ENOENT:
                raise KeyError(cpv)
            else:
                raise errors.CacheCorruption(cpv, e)

    def __contains__(self, cpv):
        return os.path.exists(pjoin(self.location, cpv))

    def iterkeys(self):
        """generator for walking the dir struct"""
        dirs = [self.location]
        len_base = len(self.location)
        while dirs:
            d = dirs.pop(0)
            for l in os.listdir(d):
                if l.endswith(".cpickle"):
                    continue
                p = pjoin(d, l)
                st = os.lstat(p)
                if stat.S_ISDIR(st.st_mode):
                    dirs.append(p)
                    continue
                yield p[len_base+1:]
