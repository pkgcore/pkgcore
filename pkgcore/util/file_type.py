# Copyright: 2008 Brian Harring <ferringb@gmail.com> 
# License: BSD/GPL2

from pkgcore.spawn import spawn_get_output

class file_identifier(object):

    def __init__(self, force_binary=False):
        if force_binary:
            self.func = self._fallback_file

    def __getattr__(self, attr):
        if attr != 'func':
            raise AttributeError(attr)
        obj = self.func = self._get_file_func()
        return obj

    def __call__(self, obj):
        if not isinstance(obj, basestring):
            obj = obj.path
        return self.func(obj)

    @classmethod
    def _get_file_func(cls):
        try:
            import magic
        except ImportError:
            return cls._fallback_file
        obj = magic.open(magic.MAGIC_NONE)
        ret = obj.load()
        if ret != 0:
            raise ValueError("non zero ret from loading magic: %s" % ret)
        return obj.file

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


