# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
data source.

Think of it as a far more minimal form of file protocol
"""

from StringIO import StringIO
from snakeoil.currying import pre_curry, alias_class_method
from snakeoil import compatibility

def generic_immutable_method(attr, self, *a, **kwds):
    raise AttributeError("%s doesn't have %s" % (self.__class__, attr))

def make_ro_cls(scope):
    scope.update([(k, pre_curry(generic_immutable_method, k)) for k in
        ["write", "writelines", "truncate"]])

class text_native_ro_StringIO(StringIO):
    make_ro_cls(locals())


class StringIO_wr_mixin(object):

    base_cls = None

    def __init__(self, callback, *args, **kwds):
        if not callable(callback):
            raise TypeError("callback must be callable")
        self.base_cls.__init__(self, *args, **kwds)
        self._callback = callback

    def close(self):
        self.flush()
        if self._callback is not None:
            self.seek(0)
            self._callback(self.read())
            self._callback = None
        self.base_cls.close(self)

class text_wr_StringIO(StringIO_wr_mixin, StringIO):
    base_cls = StringIO

text_ro_StringIO = text_native_ro_StringIO
if not compatibility.is_py3k:
    try:
        from cStringIO import StringIO as text_ro_StringIO
    except ImportError:
        pass
    bytes_ro_StringIO = text_ro_StringIO
    bytes_wr_StringIO = text_wr_StringIO
else:
    import io
    class bytes_ro_StringIO(io.BytesIO):
        make_ro_cls(locals())

    class bytes_wr_StringIO(StringIO_wr_mixin, io.BytesIO):
        base_cls = io.BytesIO


class base(object):
    """base class, all implementations should match this protocol"""
    get_fileobj = get_path = None


class local_source(base):

    """locally accessible data source"""

    __slots__ = ("path", "mutable")

    buffering_window = 32768

    def __init__(self, path, mutable=False):
        """@param path: file path of the data source"""
        base.__init__(self)
        self.path = path
        self.mutable = mutable

    def get_path(self):
        return self.path

    def get_text_fileobj(self):
        if self.mutable:
            return open(self.path, "r+", self.buffering_window)
        return open(self.path, "r", self.buffering_window)

    def get_bytes_fileobj(self):
        if self.mutable:
            return open(self.path, "rb+", self.buffering_window)
        return open(self.path, 'rb', self.buffering_window)

    get_fileobj = alias_class_method("get_text_fileobj")


class data_source(base):

    def __init__(self, data, mutable=False):
        """@param data: data to wrap"""
        base.__init__(self)
        self.data = data
        self.mutable = mutable

    get_path = None

    if compatibility.is_py3k:
        def _convert_data(self, mode):
            if mode == 'bytes':
                if isinstance(self.data, bytes):
                    return self.data
                return self.data.encode()
            if isinstance(self.data, str):
                return self.data
            return self.data.decode()
    else:
        def _convert_data(self, mode):
            return self.data

    def get_text_fileobj(self):
        if self.mutable:
            return text_wr_StringIO(self._reset_data,
                self._convert_data('text'))
        return text_ro_StringIO(self._convert_data('text'))

    if compatibility.is_py3k:
        def _reset_data(self, data):
            if isinstance(self.data, bytes):
                if not isinstance(data, bytes):
                    data = data.encode()
            elif not isinstance(data, str):
                data = data.decode()
            self.data = data
    else:
        def _reset_data(self, data):
            self.data = data

    get_fileobj = alias_class_method("get_text_fileobj")

    def get_bytes_fileobj(self):
        if self.mutable:
            return bytes_wr_StringIO(self._reset_data,
                self._convert_data('bytes'))
        return bytes_ro_StringIO(self._convert_data('bytes'))


if not compatibility.is_py3k:
    text_data_source = data_source
    bytes_data_source = data_source
else:
    class text_data_source(data_source):
        def __init__(self, data, mutable=False):
            if not isinstance(data, str):
                raise TypeError("data must be a str")
            data_source.__init__(self, data, mutable=mutable)

        def _convert_data(self, mode):
            if mode != 'bytes':
                return self.data
            return self.data.encode()

    class bytes_data_source(data_source):
        def __init__(self, data, mutable=False):
            if not isinstance(data, str):
                raise TypeError("data must be bytes")
            data_source.__init__(self, data, mutable=mutable)

        def _convert_data(self, mode):
            if mode == 'bytes':
                return self.data
            return self.data.decode()
