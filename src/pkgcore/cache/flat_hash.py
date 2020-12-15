"""
per key file based backend
"""

__all__ = ("database",)

import os
import stat

from snakeoil.fileutils import readlines_utf8
from snakeoil.osutils import pjoin

from ..config.hint import ConfigHint
from . import errors, fs_template


class database(fs_template.FsBased):
    """Stores cache entries in key=value form, stripping newlines."""

    # TODO: different way of passing in default auxdbkeys and location
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
            data = readlines_utf8(path, True, True, True)
            if data is None:
                raise KeyError(cpv)
            return self._parse_data(data, data.mtime)
        except (EnvironmentError, ValueError) as e:
            raise errors.CacheCorruption(cpv, e) from e

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
                d[self._chf_key] = int(mtime)
        else:
            d[self._chf_key] = self._chf_deserializer(d[self._chf_key])
        return d

    def _setitem(self, cpv, values):
        # might seem weird, but we rely on the trailing +1; this
        # makes it behave properly for any cache depth (including no depth)
        s = cpv.rfind('/') + 1
        fp = pjoin(self.location, cpv[:s], f'.update.{os.getpid()}.{cpv[s:]}')
        try:
            myf = open(fp, "w", 32768)
        except FileNotFoundError:
            if not self._ensure_dirs(cpv):
                raise errors.CacheCorruption(
                    cpv, f'error creating directory for {fp!r}')
            try:
                myf = open(fp, "w", 32768)
            except EnvironmentError as e:
                raise errors.CacheCorruption(cpv, e) from e
        except OSError as e:
            raise errors.CacheCorruption(cpv, e) from e

        if self._mtime_used:
            if not self.mtime_in_entry:
                mtime = values['_mtime_']
        for k, v in sorted(values.items()):
            myf.writelines(f'{k}={v}\n')

        myf.close()
        if self._mtime_used and not self.mtime_in_entry:
            self._ensure_access(fp, mtime=mtime)
        else:
            self._ensure_access(fp)

        # update written, now we move it
        new_fp = pjoin(self.location, cpv)
        try:
            os.rename(fp, new_fp)
        except EnvironmentError as e:
            os.remove(fp)
            raise errors.CacheCorruption(cpv, e) from e

    def _delitem(self, cpv):
        try:
            os.remove(pjoin(self.location, cpv))
        except FileNotFoundError:
            raise KeyError(cpv)
        except OSError as e:
            raise errors.CacheCorruption(cpv, e) from e

    def __contains__(self, cpv):
        return os.path.exists(pjoin(self.location, cpv))

    def keys(self):
        """generator for walking the dir struct"""
        dirs = [self.location]
        len_base = len(self.location)
        # Note: the misc try/except clauses are to protect against concurrent
        # modification of the cache resulting in transient errors.
        while dirs:
            d = dirs.pop(0)
            try:
                subdirs = os.listdir(d)
            except FileNotFoundError:
                continue
            except EnvironmentError as e:
                raise KeyError(cpv, f"access failure: {e}")
            for l in os.listdir(d):
                if l.endswith(".cpickle"):
                    continue
                p = pjoin(d, l)
                try:
                    st = os.lstat(p)
                except FileNotFoundError:
                    continue
                except EnvironmentError as e:
                    raise KeyError(cpv, f"Unhandled IO error: {e}")
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
        super().__init__(location, **config)
