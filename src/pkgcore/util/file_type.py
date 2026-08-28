__all__ = ("file_identifier",)

import subprocess

from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.klass import jit_attr


class file_identifier:
    def __init__(self, force_binary=False):
        if force_binary:
            self.func = self._fallback_file

    def __call__(self, obj):
        if not isinstance(obj, str):
            obj = obj.path
        return self.func(obj)

    @jit_attr
    def func(self):
        try:
            import magic
        except ImportError:
            return self._fallback_file
        if hasattr(magic, "MAGIC_NONE"):
            # <5.05 of file
            magic_const = magic.MAGIC_NONE
        else:
            magic_const = magic.NONE
        try:
            obj = magic.open(magic_const)
            ret = obj.load()
            if ret == 0:
                return obj.file
        except IGNORED_EXCEPTIONS:
            raise
        except Exception:
            pass  # POS of library.
        return self._fallback_file

    @staticmethod
    def _fallback_file(path):
        ret = subprocess.run(
            ["file", path], capture_output=True, text=True, check=False
        )
        if ret.returncode != 0:
            raise ValueError(
                f"file output was non zero- ret:{ret.returncode!r} out:{ret.stdout!r}"
            )
        out = ret.stdout
        if out.startswith(path):
            out = out[len(path) :]
            out = out.removeprefix(":")
        return out
