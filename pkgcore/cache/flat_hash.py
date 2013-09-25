# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
per key file based backend
"""

__all__ = ("database",)

import os, stat, errno
from pkgcore.cache import fs_template, errors
from pkgcore.config import ConfigHint
from snakeoil.osutils import pjoin
from snakeoil.fileutils import readlines_ascii
from snakeoil.compatibility import raise_from

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
    mtime_in_entry = True
    eclass_chf_types = ('eclassdir', 'mtime')

    def _getitem(self, cpv):
        path = pjoin(self.location, cpv)
        try:
            data = readlines_ascii(path, True, True, True)
            if data is None:
                raise KeyError(cpv)
            return self._parse_data(data, data.mtime)
        except (EnvironmentError, ValueError), e:
            raise_from(errors.CacheCorruption(cpv, e))

    def _parse_data(self, data, mtime):
        d = self._cdict_kls()
        known = self._known_keys
        for x in data:
            k, v = x.split("=", 1)
            if k in known:
                d[k] = v

        if self._mtime_used:
            if self.mtime_in_entry:
                d[self._chf_key] = self._chf_deserializer(d[self._chf_key])
            else:
                d[self._chf_key] = long(mtime)
        else:
            d[self._chf_key] = self._chf_deserializer(d[self._chf_key])
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
                except EnvironmentError, e:
                    raise_from(errors.CacheCorruption(cpv, e))
            else:
                raise_from(errors.CacheCorruption(cpv, ie))
        except OSError, e:
            raise_from(errors.CacheCorruption(cpv, e))

        if self._mtime_used:
            if not self.mtime_in_entry:
                mtime = values['_mtime_']
        for k, v in values.iteritems():
            myf.writelines("%s=%s\n" % (k, v))

        myf.close()
        if self._mtime_used and not self.mtime_in_entry:
            self._ensure_access(fp, mtime=mtime)
        else:
            self._ensure_access(fp)

        #update written.  now we move it.

        new_fp = pjoin(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except EnvironmentError, e:
            os.remove(fp)
            raise_from(errors.CacheCorruption(cpv, e))

    def _delitem(self, cpv):
        try:
            os.remove(pjoin(self.location, cpv))
        except OSError, e:
            if e.errno == errno.ENOENT:
                raise KeyError(cpv)
            else:
                raise_from(errors.CacheCorruption(cpv, e))

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


class md5_cache(database):

    chf_type = 'md5'
    eclass_chf_types = ('md5',)
    chf_base = 16

    def __init__(self, location, **config):
        location = pjoin(location, 'metadata', 'md5-cache')
        database.__init__(self, location, **config)
