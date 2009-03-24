# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
binpkg tar utilities
"""
import os, stat
from pkgcore.fs.fs import fsFile, fsDir, fsSymlink, fsFifo, fsDev
from pkgcore.fs import contents
from pkgcore.interfaces.data_source import data_source

from snakeoil.tar import tarfile
from snakeoil.currying import partial

class archive_data_source(data_source):
    def get_fileobj(self):
        return self.data()

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

def archive_to_fsobj(src_tar):
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
            d["data_source"] = archive_data_source(partial(
                    src_tar.extractfile, member.name))
            yield fsFile(location, **d)
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
    try:
        t = known_compressors[compressor](path, mode="r")
    except tarfile.ReadError, e:
        if not e.message.endswith("empty header"):
            raise
        t = []
    return convert_archive(t)


def convert_archive(archive):
    # regarding the usage of del in this function... bear in mind these sets
    # could easily have 10k -> 100k entries in extreme cases; thus the del
    # usage, explicitly trying to ensure we don't keep refs long term.

    # this one is a bit fun.
    raw = list(archive_to_fsobj(archive))
    # we use the data source as the unique key to get position.
    files_ordering = list(enumerate(x for x in raw if x.is_reg))
    files_ordering = dict((x.data_source, idx) for idx, x in files_ordering)
    t = contents.contentsSet(raw, mutable=True)
    del raw, archive

    # first rewrite affected syms.
    raw_syms = t.links()
    syms = contents.contentsSet(raw_syms)
    while True:
        for x in sorted(syms):
            affected = syms.child_nodes(x.location)
            if not affected:
                continue
            syms.difference_update(affected)
            syms.update(affected.change_offset(x.location, x.resolved_target))
            del affected
            break
        else:
            break

    t.difference_update(raw_syms)
    t.update(syms)

    del raw_syms
    syms = sorted(syms, reverse=True)
    # ok, syms are correct.  now we get the rest.
    # we shift the readds into a seperate list so that we don't reinspect
    # them on later runs; this slightly reduces the working set.
    additions = []
    for x in syms:
        affected = t.child_nodes(x.location)
        if not affected:
            continue
        t.difference_update(affected)
        additions.extend(affected.change_offset(x.location, x.resolved_target))

    t.update(additions)
    t.add_missing_directories()

    # finally... an insane sort.
    def sort_func(x, y):
        if x.is_dir:
            if not y.is_dir:
                return -1
            return cmp(x, y)
        elif y.is_dir:
            return +1
        elif x.is_reg:
            if y.is_reg:
                return cmp(files_ordering[x.data_source],
                    files_ordering[y.data_source])
            return +1
        elif y.is_reg:
            return -1
        return cmp(x, y)

    return contents.OrderedContentsSet(sorted(t, cmp=sort_func), mutable=False)
