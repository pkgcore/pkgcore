# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
cache subsystem exceptions
"""

class CacheError(Exception):
    pass

class InitializationError(CacheError):
    def __init__(self, class_name, error):
        CacheError.__init__(self, "Creation of instance %s failed due to %s" %
                            (class_name, error))
        self.error, self.class_name = error, class_name


class CacheCorruption(CacheError):
    def __init__(self, key, ex):
        CacheError.__init__(self, "%s is corrupt: %s" % (key, ex))
        self.key, self.ex = key, ex


class GeneralCacheCorruption(CacheError):
    def __init__(self, ex):
        CacheError.__init__(self, "corruption detected: %s" % (ex,))
        self.ex = ex


class InvalidRestriction(CacheError):
    def __init__(self, key, restriction, exception=None):
        if exception is None:
            exception = ''
        CacheError.__init__(self, "%s:%s is not valid: %s" %
                            (key, restriction, exception))
        self.key, self.restriction, self.ex = key, restriction, exception


class ReadOnly(CacheError):
    def __init__(self, info=''):
        CacheError.__init__(self, "cache is non-modifiable %s" % (info,))
        self.info = info
