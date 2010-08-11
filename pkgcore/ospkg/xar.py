# Copyright: 2009 PathScale
# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
binpkg xar utilities
"""
import os, stat
import subprocess
from pkgcore.fs.fs import fsFile, fsDir, fsSymlink, fsFifo, fsDev
from pkgcore.fs import contents
from snakeoil.data_source import invokable_data_source

import xarfile
from snakeoil.mappings import OrderedDict
from snakeoil.currying import partial
from snakeoil.demandload import demandload
demandload(globals(), "pkgcore.log:logger")
import pdb
from snakeoil.xml import etree


class XarContentsSet(contents.contentsSet):

    __dict_kls__ = OrderedDict


def fsobj_to_xarinfo(fsobj):
    t = xarfile.XarInfo(fsobj.location)
    if isinstance(fsobj, fsFile):
        t.type = 'file'
        t.size = fsobj.chksums["size"]
    elif isinstance(fsobj, fsDir):
        t.type = 'directory'
    elif isinstance(fsobj, fsSymlink):
        t.type = 'symlink'
        t.linkname = fsobj.target
    elif isinstance(fsobj, fsFifo):
        t.type = 'fifo'
    elif isinstance(fsobj, fsDev):
        if stat.S_ISCHR(fsobj.mode):
            t.type = 'chrtype'
        else:
            t.type = 'blktype'
        t.devmajor = fsobj.major
        t.devminor = fsobj.minor
    t.mode = fsobj.mode
    t.uid = fsobj.uid
    t.gid = fsobj.gid
    t.mtime = fsobj.mtime
    return t


def write_set(pkg_contents, pkg_package, pkg_category, pkg_fullver, pkg_cbuild, pkg_description, pkg_homepage, pkg_slot, pkg_license,  pkg_pdepends, pkg_rdepends, filepath, destdir, compressor='xz', platform='solaris'):
#def write_set(pkg_contents, filepath, destdir, compressor='gzip'):
    # Start build toc
    tempxml = destdir +  "/temp/" + "temp.xml"
    #tree = ElementTree()
    # Should not hard code this, but someone else can fix.. right?
    # XXX: that someone else hates you now.
#   tree.parse("/usr/share/pkgcore/xml/toc.xml")
#   tree.start("foo")
    root = etree.Element("ospkg", {'version': "1.0"});
    prov = etree.SubElement(root, "provides");
    name = etree.SubElement(prov, "name")
    name.text = pkg_package;
    pkgcategory = etree.SubElement(prov, "category")
    pkgcategory.text = pkg_category
    version = etree.SubElement(prov, "version")
    version.text = pkg_fullver
    pkgplatform = etree.SubElement(root, "platform")
    pkgplatform.text = platform
    arch = etree.SubElement(root, "arch")
    arch.text = "amd64"
    desc = etree.SubElement(root, "desc")
    desc.text = pkg_description
    homepage = etree.SubElement(root, "homepage")
    homepage.text = pkg_homepage
    slot = etree.SubElement(root, "slot")
    slot.text = pkg_slot
    license = etree.SubElement(root, "license")
    license.text = "%s" % (pkg_license,);

    # TODO: Part of the upcoming QA Framework
    #<!-- QA level to replace -->
    #<qalevel>0</qalevel>
    qalevel = ET.SubElement(root, "qalevel"); qalevel.text = "0";
    #<!-- Optional set of packages which all belong together.
    #  Multiple qa set items may be defined to create overlap vs monolithic sets
    #-->
    #<qaset>
    #    <item></item>
    #</qaset>
    qasets = ET.SubElement(root, "qasets");
    # For each in build variable QASETS=
    # Should a qaset item be a unique string or integer?
    # Integer will allow better tracking, but text name easier to remember
    qaitem = ET.SubElement(qasets, "item"); qaitem.text = "example-1";
    dependencies = ET.SubElement(root, "dependencies");
    # For each
    for x in pkg_rdepends.split()[:]:
        dep = ET.SubElement(dependencies, "dep"); dep.text = x; dep.attrib["type"] = "runtime";
        for x in pkg_pdepends.split()[:]:
            dep = ET.SubElement(dependencies, "dep"); dep.text = x; dep.attrib["type"] = "config";

    tree = ET.ElementTree(root)
    tree.write(tempxml)
    # End build toc

    imagedir = destdir  + "/image"
    os.chdir(imagedir)
    retcode = subprocess.call(["/usr/bin/xar" , "-cf", filepath, ".", "--compression=" + compressor , "-n" , "package_meta", "-s" , tempxml])

    # first add directories, then everything else
    # this is just a pkgcore optimization, it prefers to see the dirs first.
    os.chdir("/tmp")

def xarinfo_to_fsobj(src_xar):
    psep = os.path.sep
    for member in src_xar:
        d = {
            "uid":member.uid, "gid":member.gid,
            "mtime":member.mtime, "mode":member.mode}
        location = psep + member.name.strip(psep)
        if member.isdir():
            if member.name.strip(psep) == ".":
                continue
            yield fsDir(location, **d)
        elif member.isreg():
            d["data_source"] = invokable_data_source.wrap_function(partial(
                    src_xar.extractfile, member.name), False)
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
                "unknown type %r, %r was encounted walking xarmembers" %
                    (member, member.type))

#known_compressors = {"bz2": tarfile.TarFile.bz2open,
#    "gz": tarfile.TarFile.gzopen,
#    None: tarfile.TarFile.open}
#TODO: implement compressors
def generate_contents(path, compressor="bz2"):
    """
    generate a contentset from a tarball

    @param path: string path to location on disk
    @param compressor: defaults to bz2; decompressor to use, see
        L{known_compressors} for list of valid compressors
    """
    t = xarfile.XarArchive(path)

    # regarding the usage of del in this function... bear in mind these sets
    # could easily have 10k -> 100k entries in extreme cases; thus the del
    # usage, explicitly trying to ensure we don't keep refs long term.

    # this one is a bit fun.
    raw = list(xarinfo_to_fsobj(t))
    # we use the data source as the unique key to get position.
    files_ordering = list(enumerate(x for x in raw if x.is_reg))
    files_ordering = dict((x.data_source, idx) for idx, x in files_ordering)
    t = contents.contentsSet(raw, mutable=True)
    del raw

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

    return XarContentsSet(sorted(t, cmp=sort_func), mutable=False)
