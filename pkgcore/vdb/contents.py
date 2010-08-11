# Copyright: 2005-2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

__all__ = ("LookupFsDev", "ContentsFile")

from pkgcore.fs.contents import contentsSet
from pkgcore.fs import fs
from snakeoil import data_source

from snakeoil.fileutils import AtomicWriteFile
from snakeoil.compatibility import any
from snakeoil.demandload import demandload
demandload(globals(),
    'os',
    'stat',
    'errno',
    'snakeoil.chksum:get_handler',
    'snakeoil.osutils:readlines_ascii',
    'pkgcore:os_data',
)

class LookupFsDev(fs.fsDev):

    __slots__ = ()

    def __init__(self, path, **kwds):
        if any(x not in kwds for x in ("major", "minor", "mode")):
            try:
                st = os.lstat(path)
            except OSError, oe:
                if oe.errno != errno.ENOENT:
                    raise
                st = None
            if st is None or any(f(st.st_mode) for f in
                (stat.S_ISREG, stat.S_ISDIR, stat.S_ISFIFO)):
                kwds["strict"] = True
            else:
                major, minor = fs.get_major_minor(st)
                kwds["major"] = major
                kwds["minor"] = minor
                kwds["mode"] = st.st_mode
        fs.fsDev.__init__(self, path, **kwds)


class ContentsFile(contentsSet):
    """class wrapping a contents file"""

    def __init__(self, source, mutable=False, create=False):

        if not isinstance(source, (data_source.base, basestring)):
            raise TypeError("source must be either data_source, or a filepath")
        contentsSet.__init__(self, mutable=True)
        self._source = source

        if not create:
            self.update(self._iter_contents())

        self.mutable = mutable

    def clone(self, empty=False):
        # create is used to block it from reading.
        cset = self.__class__(self._source, mutable=True, create=True)
        if not empty:
            cset.update(self)
        return cset

    def add(self, obj):
        if isinstance(obj, fs.fsFile):
            # strict checks
            if obj.chksums is None or "md5" not in obj.chksums:
                raise TypeError("fsFile objects need to be strict")
        elif not isinstance(obj, (fs.fsDir, fs.fsSymlink, fs.fsFifo, fs.fsDev)):
            raise TypeError(
                "obj must be of fsObj, fsDir, fsLink, fsFifo, fsDev class "
                "or derivative")

        contentsSet.add(self, obj)

    def _get_fd(self, write=False):
        if isinstance(self._source, basestring):
            if write:
                return AtomicWriteFile(self._source, uid=os_data.root_uid,
                    gid=os_data.root_gid, perms=0644)
            return readlines_ascii(self._source, True)
        fobj = self._source.text_fileobj(writable=write)
        if write:
            fobj.seek(0, 0)
            fobj.truncate(0)
        return fobj

    def flush(self):
        return self._write()

    def _parse_old(self, line):
        """parse old contents, non tab based format"""
        # specifically force splitting on spaces.

    def _iter_contents(self):
        self.clear()
        for line in self._get_fd():
            if not line:
                continue
            s = line.split(" ")
            if s[0] in ("dir", "dev", "fif"):
                path = ' '.join(s[1:])
                if s[0] == 'dir':
                    obj = fs.fsDir(path, strict=False)
                elif s[0] == 'dev':
                    obj = LookupFsDev(path, strict=False)
                else:
                    obj = fs.fsFifo(path, strict=False)
            elif s[0] == "obj":
                path = ' '.join(s[1:-2])
                obj = fs.fsFile(
                    path, chksums={"md5":long(s[-2], 16)},
                        mtime=long(s[-1]), strict=False)
            elif s[0] == "sym":
                try:
                    p = s.index("->")
                    obj = fs.fsLink(' '.join(s[1:p]), ' '.join(s[p+1:-1]),
                        mtime=long(s[-1]), strict=False)

                except ValueError:
                    # XXX throw a corruption error
                    raise
            else:
                raise Exception(
                    "unknown entry type %r" % (line,))

            yield obj

    def _write(self):
        md5_handler = get_handler('md5')
        outfile = None
        try:
            outfile = self._get_fd(True)

            for obj in sorted(self):

                if isinstance(obj, fs.fsFile):
                    s = " ".join(("obj", obj.location,
                        md5_handler.long2str(obj.chksums["md5"]),
                        str(long(obj.mtime))))

                elif isinstance(obj, fs.fsLink):
                    s = " ".join(("sym", obj.location, "->",
                                   obj.target, str(long(obj.mtime))))

                elif isinstance(obj, fs.fsDir):
                    s = "dir " + obj.location

                elif isinstance(obj, fs.fsDev):
                    s = "dev " + obj.location

                elif isinstance(obj, fs.fsFifo):
                    s = "fif " + obj.location

                else:
                    raise Exception(
                        "unknown type %s: %s" % (type(obj), obj))
                outfile.write(s + "\n")
            outfile.close()

        finally:
            # if atomic, it forces the update to be wiped.
            del outfile
