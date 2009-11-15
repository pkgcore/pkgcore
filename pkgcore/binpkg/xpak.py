# Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
XPAK container support
"""

import struct
from snakeoil.mappings import OrderedDict, autoconvert_py3k_methods_metaclass
from snakeoil import klass, compatibility
from snakeoil.demandload import demandload
demandload(globals(), "os", "errno")

#
# format is:
# XPAKPACKIIIIDDDD[index][data]XPAKSTOPOOOOSTOP
# first; all ints/longs are big endian
# meanwhile, 8 byte format magic
# 4 bytes of index len,
# 4 bytes of data len
# index items: 4 bytes (len of the key name), then that length of key data
#   finally, 2 longs; relative offset from data block start, length of the data
#   repeats till index is full processed
# for data, just a big blob; offsets into it are determined via the index
#   table.
# finally, trailing magic, 4 bytes (positive) of the # of bytes to seek to
#   reach the end of the magic, and 'STOP'.  offset is relative to EOS for Xpak
#

class MalformedXpak(Exception):
    def __init__(self, msg):
        Exception.__init__(self, "xpak as malformed: %s" % (msg,))
        self.msg = msg


class Xpak(object):
    __slots__ = ("_source", "_source_is_path", "xpak_start", "_keys_dict")
    trailer_size = 16
    trailer_parser = ">8sL4s"
    trailer_pre_magic = "XPAKSTOP"
    trailer_post_magic = "STOP"

    __metaclass__ = autoconvert_py3k_methods_metaclass

    header_size = 16
    header_parser = ">8sLL"
    header_pre_magic = "XPAKPACK"

    if compatibility.is_py3k:
        trailer_post_magic = trailer_post_magic.encode("ascii")
        trailer_pre_magic = trailer_pre_magic.encode("ascii")
        header_pre_magic = header_pre_magic.encode("ascii")


    def __init__(self, source):
        self._source_is_path = isinstance(source, basestring)
        self._source = source
        self.xpak_start = None
        # keys_dict becomes an ordereddict after _load_offsets; reason for
        # it is so that reads are serialized.

    @property
    def _fd(self):
        # we do this annoying little dance to avoid having a couple
        # hundred fds open if they're accessing a lot of binpkgs
        if self._source_is_path:
            return open(self._source, "rb")
        return self._source

    @classmethod
    def write_xpak(cls, target_source, data):
        """
        write an xpak dict to disk; overwriting an xpak if it exists
        @param target_source: string path, or
            L{pkgcore.interfaces.data_source.base} derivative
        @param data: mapping instance to write into the xpak.
        @return: xpak instance
        """
        try:
            old_xpak = cls(target_source)
            # force access
            old_xpak.keys()
            start = old_xpak.xpak_start
            source_is_path = old_xpak._source_is_path
        except (MalformedXpak, IOError):
            source_is_path = isinstance(target_source, basestring)
            if source_is_path:
                try:
                    start = os.lstat(target_source).st_size
                except OSError, e:
                    if e.errno != errno.ENOENT:
                        raise
                    start = 0
            else:
                f = target_source.get_bytes_fileobj().seek(0, 2)
                start = f.tell()
        new_index = []
        new_data = []
        cur_pos = 0
        for key, val in data.iteritems():
            if compatibility.is_py3k:
                key = key.encode()
                if isinstance(val, str):
                    val = val.encode()
            new_index.append(struct.pack(">L%isLL" % len(key),
                len(key), key, cur_pos, len(val)))
            new_data.append(val)
            cur_pos += len(val)

        if source_is_path:
            # rb+ required since A) binary, B) w truncates from the getgo
            handle = open(target_source, "r+b")
        else:
            handle = target_source.get_bytes_fileobj()

        joiner = ''
        if compatibility.is_py3k:
            # can't do str.join(bytes), thus this.
            joiner = joiner.encode()
        new_index = joiner.join(new_index)
        new_data = joiner.join(new_data)

        handle.seek(start, 0)
        # +12 is len(key) long, data_offset long, data_offset len long
        handle.write(struct.pack(">%isLL%is%is%isL%is" %
                (len(cls.header_pre_magic),
                len(new_index),
                len(new_data),
                len(cls.trailer_pre_magic),
                len(cls.trailer_post_magic)),
            cls.header_pre_magic,
            len(new_index),
            len(new_data),
            new_index,
            new_data,
            cls.trailer_pre_magic,
            # the fun one; 16 for the footer, 8 for index/data longs,
            # + index/data chunks.
            len(new_index) + len(new_data) + 24,
            cls.trailer_post_magic))

        handle.truncate()
        handle.close()
        return Xpak(target_source)

    @klass.jit_attr
    def keys_dict(self):
        fd = self._fd
        index_start, index_len, data_len = self._check_magic(fd)
        data_start = index_start + index_len
        keys_dict = OrderedDict()
        while index_len:
            key_len = struct.unpack(">L", fd.read(4))[0]
            key = fd.read(key_len)
            if compatibility.is_py3k:
                key = key.decode('ascii')
            if len(key) != key_len:
                raise MalformedXpak(
                    "tried reading key %i of len %i, but hit EOF" % (
                        len(keys_dict) + 1, key_len))
            try:
                offset, data_len = struct.unpack(">LL", fd.read(8))
            except struct.error:
                raise MalformedXpak(
                    "key %i, tried reading data offset/len but hit EOF" % (
                        len(keys_dict) + 1))
            keys_dict[key] = (data_start + offset, data_len,
                compatibility.is_py3k and not key.startswith("environment"))
            index_len -= (key_len + 12) # 12 for key_len, offset, data_len longs

        return keys_dict

    def _check_magic(self, fd):
        fd.seek(-16, 2)
        try:
            pre, size, post = struct.unpack(
                self.trailer_parser, fd.read(self.trailer_size))
            if pre != self.trailer_pre_magic or post != self.trailer_post_magic:
                raise MalformedXpak(
                    "not an xpak segment, trailer didn't match: %r" % fd)
        except struct.error:
            raise MalformedXpak(
                "not an xpak segment, failed parsing trailer: %r" % fd)

        # this is a bit daft, but the format seems to intentionally
        # have an off by 8 in the offset address. presumably cause the
        # header was added after the fact, either way we go +8 to
        # check the header magic.
        fd.seek(-(size + 8), 2)
        self.xpak_start = fd.tell()
        try:
            pre, index_len, data_len = struct.unpack(
                self.header_parser, fd.read(self.header_size))
            if pre != self.header_pre_magic:
                raise MalformedXpak(
                    "not an xpak segment, header didn't match: %r" % fd)
        except struct.error:
            raise MalformedXpak(
                "not an xpak segment, failed parsing header: %r" % fd)

        return self.xpak_start + self.header_size, index_len, data_len

    def keys(self):
        return list(self.iterkeys())

    def values(self):
        return list(self.itervalues())

    def items(self):
        return list(self.iteritems())

    def __len__(self):
        return len(self.keys_dict)

    def __contains__(self, key):
        return key in self.keys_dict

    def __nonzero__(self):
        return bool(self.keys_dict)

    def __iter__(self):
        return iter(self.keys_dict)

    def iterkeys(self):
        return self.keys_dict.iterkeys()

    def itervalues(self):
        fd = self._fd
        return (self._get_data(fd, *v) for v in self.keys_dict.itervalues())

    def iteritems(self):
        # note that it's an OrderedDict, so this works.
        fd = self._fd
        return (
            (k, self._get_data(fd, *v))
            for k, v in self.keys_dict.iteritems())

    def __getitem__(self, key):
        return self._get_data(self._fd, *self.keys_dict[key])

    def __delitem__(self, key):
        del self.keys_dict[key]

    def __setitem__(self, key, val):
        self.keys_dict[key] = val
        return val

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *a):
        # faster then the exception form...
        l = len(a)
        if l > 1:
            raise TypeError("pop accepts 1 or 2 args only")
        if key in self.keys_dict:
            o = self.keys_dict.pop(key)
        elif l:
            o = a[0]
        else:
            raise KeyError(key)
        return o

    def _get_data(self, fd, offset, data_len, needs_decoding=False):
        # optimization for file objs; they cache tell position, but
        # pass through all seek calls (nice, eh?) so we rely on that
        # for cutting down on uneeded seeks; userland comparison being
        # far cheaper then an actual syscall seek
        if fd.tell() != offset:
            fd.seek(offset, 0)
        assert fd.tell() == offset
        r = fd.read(data_len)
        assert len(r) == data_len
        if needs_decoding:
            return r.decode()
        return r
