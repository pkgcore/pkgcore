# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


"""
default chksum handlers implementation- sha1, sha256, rmd160, and md5
"""
from pkgcore.interfaces.data_source import base as base_data_source
from snakeoil.currying import partial
from snakeoil import modules
from snakeoil.compatibility import intern, is_py3k
from snakeoil.demandload import demandload
demandload(globals(), "os")

blocksize = 32768

sha1_size = 40
md5_size = 32
rmd160_size = 40
sha256_size = 64

def loop_over_file(filename, *objs):
    if isinstance(filename, base_data_source):
        if filename.get_path is not None:
            filename = filename.get_path()
        else:
            filename = filename.get_fileobj()
    wipeit = False
    if isinstance(filename, basestring):
        wipeit = True
        f = open(filename, 'rb', blocksize * 2)
    else:
        f = filename
        # reposition to start
        f.seek(0, 0)
    try:
        chfs = [chf() for chf in objs]
        if hasattr(f, 'getvalue'):
            data = f.getvalue()
            if is_py3k:
                if not isinstance(data, bytes):
                    data = data.encode("ascii")
            for chf in chfs:
                chf.update(data)
        elif is_py3k:
            data = f.read(blocksize)
            if isinstance(data, bytes):
                convert = lambda x:x
            else:
                convert = lambda x:x.encode("ascii")
                data = convert(data)
            while data:
                for chf in chfs:
                    # this probably is wrong...
                    chf.update(data)
                data = convert(f.read(blocksize))
        else:
            data = f.read(blocksize)
            while data:
                for chf in chfs:
                    chf.update(data)
                data = f.read(blocksize)

        return [long(chf.hexdigest(), 16) for chf in chfs]
    finally:
        if wipeit:
            f.close()


class Chksummer(object):

    def __init__(self, chf_type, obj, str_size):
        self.obj = obj
        self.chf_type = chf_type
        self.str_size = str_size

    def new(self):
        return self.obj

    def long2str(self, val):
        return ("%x" % val).rjust(self.str_size, '0')

    @staticmethod
    def str2long(val):
        return long(val, 16)

    def __call__(self, filename):
        return loop_over_file(filename, self.obj)[0]

    def __str__(self):
        return "%s chksummer" % self.chf_type


# We have a couple of options:
#
# - If we are on python 2.5 or newer we can use hashlib, which uses
#   openssl if available (this will be fast and support a whole bunch
#   of hashes) and use a c implementation from python itself otherwise
#   (does not support as many hashes, slower).
# - On older pythons we can use the sha and md5 module for sha1 and md5.
#	On python 2.5 these are deprecated wrappers around hashlib.
# - On any python we can use the fchksum module (if available) which can
#   hash an entire file faster than we can, probably just because it does the
#   file-reading and hashing both in c.
# - For any python we can use PyCrypto. Supports many hashes, fast but not
#   as fast as openssl-powered hashlib. Not compared to cpython hashlib.
#
# To complicate matters hashlib has a couple of hashes always present
# as attributes of the hashlib module and less common hashes available
# through a constructor taking a string. The former is faster.
#
# Some timing data from my athlonxp 2600+, python 2.4.3, python 2.5rc1,
# pycrypto 2.0.1-r5, openssl 0.9.7j, fchksum 1.7.1 (not exhaustive obviously):
# (test file is the Python 2.4.3 tarball, 7.7M)
#
# python2.4 -m timeit -s 'import fchksum'
#   'fchksum.fmd5t("/home/marienz/tmp/Python-2.4.3.tar.bz2")[0]'
# 40 +/- 1 msec roughly
#
# same with python2.5: same results.
#
# python2.4 -m timeit -s 'from pkgcore.chksum import defaults;import md5'
#   'defaults.loop_over_file(md5, "/home/marienz/tmp/Python-2.4.3.tar.bz2")'
# 64 +/- 1 msec roughly
#
# Same with python2.5:
# 37 +/- 1 msec roughly
#
# python2.5 -m timeit -s
#   'from pkgcore.chksum import defaults; from snakeoil import currying;'
# -s 'import hashlib; hash = currying.pre_curry(hashlib.new, "md5")'
#   'defaults.loop_over_file(hash, "/home/marienz/tmp/Python-2.4.3.tar.bz2")'
# 37 +/- 1 msec roughly
#
# python2.5 -m timeit -s 'import hashlib'
#   'h=hashlib.new("md5"); h.update("spork"); h.hexdigest()'
# 6-7 usec per loop
#
# python2.5 -m timeit -s 'import hashlib'
#   'h=hashlib.md5(); h.update("spork"); h.hexdigest()'
# ~4 usec per loop
#
# python2.5 -m timeit -s 'import hashlib;data = 1024 * "spork"'
#   'h=hashlib.new("md5"); h.update(data); h.hexdigest()'
# ~20 usec per loop
#
# python2.5 -m timeit -s 'import hashlib;data = 1024 * "spork"'
#   'h=hashlib.md5(); h.update(data); h.hexdigest()'
# ~18 usec per loop
#
# Summarized:
# - hashlib is faster than fchksum, fchksum is faster than python 2.4's md5.
# - using hashlib's new() instead of the predefined type is still noticably
#   slower for 5k of data. Since ebuilds and patches will often be smaller
#   than 5k we should avoid hashlib's new if there is a predefined type.
# - If we do not have hashlib preferring fchksum over python md5 is worth it.
# - Testing PyCrypto is unnecessary since its Crypto.Hash.MD5 is an
#   alias for python's md5 (same for sha1).
#
# An additional advantage of using hashlib instead of PyCrypto is it
# is more reliable (PyCrypto has a history of generating bogus hashes,
# especially on non-x86 platforms, OpenSSL should be more reliable
# because it is more widely used).
#
# TODO do benchmarks for more hashes?
#
# Hash function we use is:
# - hashlib attr if available
# - hashlib through new() if available.
# - fchksum with python md5 fallback if possible
# - PyCrypto
# - python's md5 or sha1.

chksum_types = {}

try:
    import hashlib
except ImportError:
    pass
else:
    # Always available according to docs.python.org:
    # md5(), sha1(), sha224(), sha256(), sha384(), and sha512().
    for hashlibname, chksumname, size in [
        ('md5', 'md5', md5_size),
        ('sha1', 'sha1', sha1_size),
        ('sha256', 'sha256', sha256_size),
        ]:
        chksum_types[chksumname] = Chksummer(chksumname,
            getattr(hashlib, hashlibname), size)

    # May or may not be available depending on openssl. List
    # determined through trial and error.
    for hashlibname, chksumname in [
        ('ripemd160', 'rmd160'),
        ]:
        try:
            hashlib.new(hashlibname)
        except ValueError:
            pass # This hash is not available.
        else:
            chksum_types[chksumname] = Chksummer(chksumname,
                partial(hashlib.new, hashlibname), rmd160_size)
    del hashlibname, chksumname


if 'md5' not in chksum_types:
    import md5
    fchksum = None
    try:
        import fchksum
    except ImportError:
        pass
    else:
        class MD5Chksummer(Chksummer):
            chf_type = "md5"
            str_size = md5_size
            __init__ = lambda s:None

            def new(self):
                return md5.new

            def __call__(self, filename):
                if isinstance(filename, base_data_source):
                    if filename.get_path is not None:
                        filename = filename.get_path()
                if isinstance(filename, basestring) and fchksum is not None:
                    return long(fchksum.fmd5t(filename)[0], 16)
                return loop_over_file(filename, md5.new)[0]

        chksum_types["md5"] = MD5Chksummer()


# expand this to load all available at some point
for k, v, str_size in (("sha1", "SHA", sha1_size),
    ("sha256", "SHA256", sha256_size),
    ("rmd160", "RIPEMD", rmd160_size)):
    if k in chksum_types:
        continue
    try:
        chksum_types[k] = Chksummer(k, modules.load_attribute(
            "Crypto.Hash.%s.new" % v), str_size)
    except modules.FailedImport:
        pass
del k, v


for modulename, chksumname, size in [
    ('sha', 'sha1', sha1_size),
    ('md5', 'md5', md5_size),
    ]:
    if chksumname not in chksum_types:
        chksum_types[chksumname] = Chksummer(chksumname,
            modules.load_attribute('%s.new' % (modulename,)), size)
del modulename, chksumname

class SizeUpdater(object):

    def __init__(self):
        self.count = 0

    def update(self, data):
        self.count += len(data)

    def hexdigest(self):
        return "%x" % self.count


class SizeChksummer(Chksummer):
    """
    size based chksum handler
    yes, aware that size isn't much of a chksum. ;)
    """

    def __init__(self):
        pass
    obj = SizeUpdater
    str_size = 1000000000
    chf_type = 'size'

    @staticmethod
    def long2str(val):
        return str(val)

    @staticmethod
    def str2long(val):
        return long(val)

    def __call__(self, file_obj):
        if isinstance(file_obj, base_data_source):
            if file_obj.get_path is not None:
                file_obj = file_obj.get_path()
            else:
                file_obj = file_obj.get_fileobj()
        if isinstance(file_obj, basestring):
            try:
                st_size = os.lstat(file_obj).st_size
            except OSError:
                return None
            return st_size
        # seek to the end.
        file_obj.seek(0, 2)
        return long(file_obj.tell())


chksum_types["size"] = SizeChksummer()
chksum_types = dict((intern(k), v) for k, v in chksum_types.iteritems())
