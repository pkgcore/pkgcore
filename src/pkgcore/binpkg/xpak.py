"""
XPAK container support
"""

__all__ = ("MalformedXpak", "Xpak")

import os
from collections import OrderedDict

from snakeoil import klass
from snakeoil import struct_compat as struct

from ..exceptions import PkgcoreException

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


class MalformedXpak(PkgcoreException):

    def __init__(self, msg):
        super().__init__(f"xpak as malformed: {msg}")
        self.msg = msg


class Xpak:
    __slots__ = ("_source", "_source_is_path", "xpak_start", "_keys_dict")

    _reading_key_rewrites = {'repo': 'REPO'}

    trailer_pre_magic = "XPAKSTOP"
    trailer_post_magic = "STOP"
    trailer = struct.Struct(">%isL%is" % (
        len(trailer_pre_magic), len(trailer_post_magic)))

    header_pre_magic = "XPAKPACK"
    header = struct.Struct(">%isLL" % (len(header_pre_magic),))

    trailer_post_magic = trailer_post_magic.encode("ascii")
    trailer_pre_magic = trailer_pre_magic.encode("ascii")
    header_pre_magic = header_pre_magic.encode("ascii")

    def __init__(self, source):
        self._source_is_path = isinstance(source, str)
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

        :param target_source: string path, or \
          :obj:`snakeoil.data_source.base` derivative
        :param data: mapping instance to write into the xpak.
        :return: xpak instance
        """
        try:
            old_xpak = cls(target_source)
            # force access
            list(old_xpak.keys())
            start = old_xpak.xpak_start
            source_is_path = old_xpak._source_is_path
        except (MalformedXpak, IOError):
            source_is_path = isinstance(target_source, str)
            if source_is_path:
                try:
                    start = os.lstat(target_source).st_size
                except FileNotFoundError:
                    start = 0
            else:
                f = target_source.bytes_fileobj(writable=True)
                f.seek(0, 2)
                start = f.tell()
        new_index = []
        new_data = []
        cur_pos = 0
        for key, val in data.items():
            if isinstance(val, str):
                val = val.encode('utf8')
            if isinstance(key, str):
                key = key.encode()
            new_index.append(struct.pack(
                ">L%isLL" % len(key),
                len(key), key, cur_pos, len(val)))
            new_data.append(val)
            cur_pos += len(val)

        if source_is_path:
            # rb+ required since A) binary, B) w truncates from the getgo
            handle = open(target_source, "r+b")
        else:
            handle = target_source.bytes_fileobj(writable=True)

        joiner = b''
        new_index = joiner.join(new_index)
        new_data = joiner.join(new_data)

        handle.seek(start, 0)
        cls.header.write(
            handle, cls.header_pre_magic, len(new_index), len(new_data))

        handle.write(struct.pack(
            ">%is%is" % (len(new_index), len(new_data)), new_index, new_data))

        # the +8 is for the longs for new_index/new_data
        cls.trailer.write(
            handle, cls.trailer_pre_magic,
            len(new_index) + len(new_data) + cls.trailer.size + 8,
            cls.trailer_post_magic)
        handle.truncate()
        handle.close()
        return Xpak(target_source)

    @klass.jit_attr
    def keys_dict(self):
        fd = self._fd
        index_start, index_len, data_len = self._check_magic(fd)
        data_start = index_start + index_len
        keys_dict = OrderedDict()
        key_rewrite = self._reading_key_rewrites.get
        while index_len:
            key_len = struct.unpack(">L", fd.read(4))[0]
            key = fd.read(key_len)
            key = key.decode('ascii')
            if len(key) != key_len:
                raise MalformedXpak(
                    "tried reading key %i of len %i, but hit EOF" % (
                        len(keys_dict) + 1, key_len))
            try:
                offset, data_len = struct.unpack(">LL", fd.read(8))
            except struct.error as e:
                raise MalformedXpak(
                    "key %i, tried reading data offset/len but hit EOF" % (
                        len(keys_dict) + 1)) from e
            key = key_rewrite(key, key)
            keys_dict[key] = (
                data_start + offset, data_len,
                not key.startswith("environment"))
            index_len -= (key_len + 12) # 12 for key_len, offset, data_len longs

        return keys_dict

    def _check_magic(self, fd):
        fd.seek(-16, 2)
        try:
            pre, size, post = self.trailer.read(fd)
            if pre != self.trailer_pre_magic or post != self.trailer_post_magic:
                raise MalformedXpak(
                    "not an xpak segment, trailer didn't match: %r" % fd)
        except struct.error as e:
            raise MalformedXpak(
                "not an xpak segment, failed parsing trailer: %r" % fd) from e

        # this is a bit daft, but the format seems to intentionally
        # have an off by 8 in the offset address. presumably cause the
        # header was added after the fact, either way we go +8 to
        # check the header magic.
        fd.seek(-(size + 8), 2)
        self.xpak_start = fd.tell()
        try:
            pre, index_len, data_len = self.header.read(fd)
            if pre != self.header_pre_magic:
                raise MalformedXpak(
                    "not an xpak segment, header didn't match: %r" % fd)
        except struct.error as e:
            raise MalformedXpak(
                "not an xpak segment, failed parsing header: %r" % fd) from e

        return self.xpak_start + self.header.size, index_len, data_len

    def keys(self):
        return self.keys_dict.keys()

    def values(self):
        fd = self._fd
        return (self._get_data(fd, *v) for v in self.keys_dict.values())

    def items(self):
        # note that it's an OrderedDict, so this works.
        fd = self._fd
        return (
            (k, self._get_data(fd, *v))
            for k, v in self.keys_dict.items())

    def __len__(self):
        return len(self.keys_dict)

    def __contains__(self, key):
        return key in self.keys_dict

    def __bool__(self):
        return bool(self.keys_dict)

    def __iter__(self):
        return iter(self.keys_dict)

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
