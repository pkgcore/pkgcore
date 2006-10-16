# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
binpkg tar utilities
"""
import os, stat
from pkgcore.util.tar import tarfile
from pkgcore.fs.fs import fsFile, fsDir, fsSymlink, fsFifo, fsDev
from pkgcore.fs import contents
from pkgcore.util.mappings import OrderedDict, StackedDict
from pkgcore.interfaces.data_source import data_source
from pkgcore.util.currying import partial

class tar_data_source(data_source):

    def get_fileobj(self):
        return self.data()

class TarContentsSet(contents.contentsSet):

    def __init__(self, initial=None, mutable=False):
        contents.contentsSet.__init__(self, mutable=True)
        self._dict = OrderedDict()
        if initial is not None:
            for x in initial:
                self.add(x)
        self.mutable = mutable


known_compressors = {"bz2": tarfile.TarFile.bz2open,
    "gz": tarfile.TarFile.gzopen,
    None: tarfile.TarFile.open}

def write_set(contents_set, filepath, compressor='bz2'):
    if compressor not in known_compressors:
        raise ValueError("compression must be one of %r, got %r" % 
            (known_compressors.keys(), compressor))
    tar_fd = known_compressors[compressor](filepath, mode="w")

    # first add directories, then everything else
    # this is just a pkgcore optimization, it prefers to see the dirs first.
    dirs = contents_set.dirs()
    dirs.sort()
    for x in dirs:
        tar_fd.addfile(fsobj_to_tarinfo(x))
    del dirs
    for x in contents_set.iterdirs(invert=True):
        t = fsobj_to_tarinfo(x)
        if t.isreg():
            tar_fd.addfile(t, fileobj=x.data.get_fileobj())
        else:
            tar_fd.addfile(t)
    tar_fd.close()

def tarinfo_to_fsobj(src_tar):
    psep = os.path.sep
    for member in src_tar:
        d = {
            "uid":member.uid, "gid":member.gid,
            "mtime":member.mtime, "mode":member.mode}
        location = psep + member.name.strip(psep)
        if member.isdir():
            if member.name.strip(psep) == ".":
                continue
            yield fsDir(location, **d)
        elif member.isreg():
            d["data_source"] = tar_data_source(partial(
                    src_tar.extractfile, member.name))
            # bit of an optimization; basically, we know size, so 
            # we stackdict it so that the original value is used, rather then
            # triggering an full chksum run for size
            f = fsFile(location, **d)
            object.__setattr__(f, "chksums", StackedDict(
                {"size":long(member.size)}, f.chksums))
            yield f
        elif member.issym() or member.islnk():
            yield fsSymlink(location, member.linkname, **d)
        elif member.isfifo():
            yield fsFifo(location, **d)
        elif member.isdev():
            d["major"] = long(member.major)
            d["minor"] = long(member.minor)
            yield fsDev(location, **d)
        else:
            raise AssertionError(
                "unknown type %r, %r was encounted walking tarmembers" %
                    (member, member.type))

def fsobj_to_tarinfo(fsobj):
    t = tarfile.TarInfo()
    if isinstance(fsobj, fsFile):
        t.type = tarfile.REGTYPE
        t.size = fsobj.chksums["size"]
    elif isinstance(fsobj, fsDir):
        t.type = tarfile.DIRTYPE
    elif isinstance(fsobj, fsSymlink):
        t.type = tarfile.SYMTYPE
        t.linkname = fsobj.target
    elif isinstance(fsobj, fsFifo):
        t.type = tarfile.FIFOTYPE
    elif isinstance(fsobj, fsDev):
        if stat.S_ISCHR(fsobj.mode):
            t.type = tarfile.CHRTYPE
        else:
            t.type = tarfile.BLKTYPE
        t.devmajor = fsobj.major
        t.devminor = fsobj.minor
    t.name = fsobj.location
    t.mode = fsobj.mode
    t.uid = fsobj.uid
    t.gid = fsobj.gid
    t.mtime = fsobj.mtime
    return t

def generate_contents(path, compressor="bz2"):
    """
    generate a contentset from a tarball
    
    @param path: string path to location on disk
    @param compressor: defaults to bz2; decompressor to use, see 
        L{known_compressors} for list of valid compressors
    """
    if compressor not in known_compressors:
        raise ValueError("compressor needs to be one of %r, got %r" % 
            (known_compressors.keys(), compressor))
    t = known_compressors[compressor](path, mode="r")
    return TarContentsSet(tarinfo_to_fsobj(t), mutable=False)
