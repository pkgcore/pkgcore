#!/usr/bin/python3
# Copyright: 2009-2011 Brian Harring <ferringb@gmail.com>
# License: PSF-2.2/GPL2/BSD

"""
python 2to3 with caching support

"""

import lib2to3.main
import lib2to3.refactor
import os, hashlib, logging, sys

def md5_hash_data(data):
    chf = hashlib.md5()
    chf.update(data)
    return chf.hexdigest()


class caching_mixin(object):

    """
    core caching logic

    Roughly, this works by intercepting 2to3 converter methods and checking
    a cache directory (defined by environment variable PY2TO3_CACHEDIR) for
    previous conversion attempts for this file.

    If the md5sum for the source matches the original conversion attempt, the
    original results are returned greatly speeding up repeated 2to3 conversions.

    If the md5sum doesn't match, it does the 2to3 conversion and than stashes a copy
    of the results into the cache dir for future usage.
    """

    base_cls = None

    @property
    def cache_dir(self):
        return os.environ.get("PY2TO3_CACHEDIR", "cache")

    def get_cache_path(self, cache_key):
        return os.path.join(self.cache_dir, cache_key)

    def update_cache_from_file(self, cache_key, filename, encoding, new_text=None):
        cache_dir = self.cache_dir
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        if new_text is None:
            f = open(filename, 'rb').read()
            # annoying, but we do this since we force encoding further down
            new_text = f.read().decode(encoding)
            f.close()
        f = None
        try:
            f = open(os.path.join(cache_dir, cache_key), 'wb')
            f.write(new_text.encode(encoding))
        finally:
            if f is not None:
                f.close()

    def check_cache(self, cache_key, encoding):
        cache_path = self.get_cache_path(cache_key)
        if os.path.isfile(cache_path):
            return open(cache_path, 'rb').read().decode(encoding)
        return None

    @staticmethod
    def compute_cache_key(input, encoding):
        return md5_hash_data(input.encode(encoding))

    def refactor_file(self, filename, write=False, doctests_only=False):
        input, encoding = self._read_python_source(filename)
        cache_key = self.compute_cache_key(input, encoding)
        cache_data = self.check_cache(cache_key, encoding)

        try:
            if not write or cache_data is None:
                return super(caching_mixin, self).refactor_file(
                    filename, write=write, doctests_only=doctests_only)
            else:
                self.processed_file(cache_data, filename, write=write,
                                    encoding=encoding, old_text=input)
        except Exception:
            logging.exception("Failed processing %s", filename)
            raise

    def processed_file(self, new_text, filename, old_text=None, write=False,
                       encoding=None):
        if write:
            if old_text is None:
                cache_key = self.compute_cache_key(*self._read_python_source(filename))
            else:
                cache_key = self.compute_cache_key(old_text, encoding)
            self.update_cache_from_file(cache_key, filename, encoding,
                                        new_text=new_text)
        return super(caching_mixin, self).processed_file(
            new_text, filename, old_text=old_text, write=write, encoding=encoding)


class RefactoringTool(caching_mixin, lib2to3.refactor.RefactoringTool):
    pass

multiprocessing_available = False
try:
    # multiprocessing semaphores require rwx permissions on shared memory for Linux
    if not hasattr(lib2to3.refactor, 'MultiprocessRefactoringTool') or \
            ('linux' in sys.platform and not os.access('/dev/shm', os.R_OK|os.W_OK|os.X_OK)):
        raise ImportError()
    # pylint: disable=unused-import
    import multiprocessing
    # this is to detect python upstream bug 3770
    from _multiprocessing import SemLock
    multiprocessing_available = True
except ImportError:
    MultiprocessRefactoringTool = RefactoringTool
else:
    class MultiprocessRefactoringTool(caching_mixin, lib2to3.refactor.MultiprocessRefactoringTool):
        pass


class my_StdoutRefactoringTool(caching_mixin, lib2to3.main.StdoutRefactoringTool):
    base_cls = lib2to3.main.StdoutRefactoringTool


def StdoutRefactoringTool(*args):
    # stupid hacks...
    lib2to3.main.StdoutRefactoringTool = my_StdoutRefactoringTool.base_cls
    inst = my_StdoutRefactoringTool.base_cls(*args)
    inst.__class__ = my_StdoutRefactoringTool
    return inst

if __name__ == '__main__':
    lib2to3.main.StdoutRefactoringTool = StdoutRefactoringTool
    sys.exit(lib2to3.main.main("lib2to3.fixes"))
