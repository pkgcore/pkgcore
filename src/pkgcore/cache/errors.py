"""
cache subsystem exceptions
"""

__all__ = (
    "CacheError", "InitializationError", "CacheCorruption",
    "GeneralCacheCorruption", "ReadOnly",
)

from ..exceptions import PkgcoreException


class CacheError(PkgcoreException):
    pass


class InitializationError(CacheError):
    def __init__(self, class_name, error):
        super().__init__(
            f'creation of instance {class_name} failed due to {error}')
        self.error, self.class_name = error, class_name


class CacheCorruption(CacheError):
    def __init__(self, key, ex):
        super().__init__(f'{key} is corrupt: {ex}')
        self.key, self.ex = key, ex


class GeneralCacheCorruption(CacheError):
    def __init__(self, ex):
        super().__init__(f'corruption detected: {ex}')
        self.ex = ex


class ReadOnly(CacheError):
    def __init__(self, info=''):
        super().__init__(f'cache is non-modifiable {info}')
        self.info = info
