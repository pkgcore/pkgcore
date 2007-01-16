# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
data source.

Think of it as a far more minimal form of file protocol
"""
from pkgcore.util.currying import pre_curry

import StringIO

def generic_immutable_method(attr, self, *a, **kwds):
    raise AttributeError("%s doesn't have %s" % (self.__class__, attr))

class native_ro_StringIO(StringIO.StringIO):
    locals().update([(k, pre_curry(generic_immutable_method, k)) for k in
        ["write", "writelines", "truncate"]])

del generic_immutable_method

class write_StringIO(StringIO.StringIO):

    def __init__(self, callback, *args, **kwds):
        if not callable(callback):
            raise TypeError("callback must be callable")
        StringIO.StringIO.__init__(self, *args, **kwds)
        self._callback = callback

    def close(self):
        self.flush()
        if self._callback is not None:
            self.seek(0)
            self._callback(self.read())
            self._callback = None
        StringIO.StringIO.close(self)

try:
    import cStringIO
    read_StringIO = cStringIO.StringIO
except ImportError:
    read_StringIO = native_ro_StringIO

class base(object):
    """base class, all implementations should match this protocol"""
    get_fileobj = get_path = None


class local_source(base):

    """locally accessible data source"""

    __slots__ = ("path", "mutable")

    def __init__(self, path, mutable=False):
        """@param path: file path of the data source"""
        base.__init__(self)
        self.path = path
        self.mutable = mutable

    def get_path(self):
        return self.path

    def get_fileobj(self):
        if self.mutable:
            return open(self.path, "rb+", 32768)
        return open(self.path, "rb", 32768)


class data_source(base):

    def __init__(self, data, mutable=False):
        """@param data: data to wrap"""
        base.__init__(self)
        self.data = data
        self.mutable = mutable

    get_path = None

    def get_fileobj(self):
        if self.mutable:
            return write_StringIO(self._reset_data, self.data)
        return read_StringIO(self.data)

    def _reset_data(self, data):
        self.data = data
