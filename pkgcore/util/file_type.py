# Copyright: 2008-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

__all__ = ("file_identifier",)

from pkgcore.spawn import spawn_get_output
from snakeoil.klass import jit_attr
from snakeoil import compatibility

class file_identifier(object):

    def __init__(self, force_binary=False):
        if force_binary:
            self.func = self._fallback_file

    def __call__(self, obj):
        if not isinstance(obj, basestring):
            obj = obj.path
        return self.func(obj)

    @jit_attr
    def func(self):
        try:
            import magic
        except ImportError:
            return self._fallback_file
        if hasattr(magic, 'MAGIC_NONE'):
            # <5.05 of file
            magic_const = magic.MAGIC_NONE
        else:
            magic_const = magic.NONE
        try:
            obj = magic.open(magic_const)
            ret = obj.load()
            if ret == 0:
                return obj.file
        except compatibility.IGNORED_EXCEPTIONS:
            raise
        except Exception:
            pass # POS of library.
        return self._fallback_file

    @staticmethod
    def _fallback_file(path):
        ret, out = spawn_get_output(["file", path])
        if ret != 0:
            raise ValueError("file output was non zero- ret:%r out:%r" %
                (ret, out))
        out = ''.join(out)
        if out.startswith(path):
            out = out[len(path):]
            if out.startswith(":"):
                out = out[1:]
        return out


