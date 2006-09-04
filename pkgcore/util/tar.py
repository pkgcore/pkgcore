# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
tar file access

monkey patching of stdlib tarfile to reduce mem usage (33% reduction).

note this is also racey; N threads trying an import, if they're after
the *original* tarfile, they may inadvertantly get ours.
"""

import sys
t=sys.modules.pop("tarfile", None)
tarfile = __import__("tarfile")
if t is not None:
    sys.modules["tarfile"] = t
else:
    del sys.modules["tarfile"]
del t
# ok, we now have our own local copy to monkey patch

class TarInfo(tarfile.TarInfo):
    __slots__ = (
        "name", "mode", "uid", "gid", "size", "mtime", "chksum", "type",
        "linkname", "uname", "gname", "devmajor", "devminor", "prefix", "offset",
        "offset_data", "buf", "sparse", "_link_target")

tarfile.TarInfo = TarInfo
# finished monkey patching.  now to lift things out of our tarfile module into this scope so from/import behaves properly.

for x in tarfile.__all__:
    locals()[x] = getattr(tarfile, x)
del x
