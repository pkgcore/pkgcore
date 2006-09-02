# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
XPAK container support
"""

from pkgcore.util.mappings import OrderedDict
import struct

# format is:
# XPAKPACKIIIIDDDD[index][data]XPAKSTOPOOOOSTOP


class MalformedXpak(Exception):
	def __init__(self, msg):
		self.msg = msg
	def __str__(self):
		return "xpak as malformed: %s" % self.msg


class Xpak(object):
	__slots__ = ("_source", "_source_is_path", "xpak_start", "_keys_dict")
	trailer_size = 16
	trailer_parser = ">8sl4s"
	trailer_pre_magic = "XPAKSTOP"
	trailer_post_magic = "STOP"

	header_size = 16
	header_parser = ">8sll"
	header_pre_magic = "XPAKPACK"
	

	def __init__(self, source, writable=False):
		self._source_is_path = isinstance(source, basestring)
		self._source = source
		self.xpak_start = None
		# this becomes an ordereddict after _load_offsets; reason for it is so that reads are serialized.
		self._keys_dict = {}
		if not writable:
			self._load_offsets()
	
	@property
	def _fd(self):
		# we do this annoying little dance to avoid having a couple hundred fds open if they're accessing a lot of binpkgs
		if self._source_is_path:
			return open(self._source, "r")
		return self._source

	def _load_offsets(self):
		fd = self._fd
		index_start, index_len, data_len = self._check_magic(fd)
		data_start = index_start + index_len
		keys_dict = OrderedDict()
		while index_len:
			key_len = struct.unpack(">l", fd.read(4))[0]
			key = fd.read(key_len)
			if len(key) != key_len:
				raise MalformedXpak("tried reading key %i of len %i, but hit EOF" % (len(keys_dict) + 1, key_len))
			try:
				offset, data_len = struct.unpack(">ll", fd.read(8))
			except struct.error:
				raise MalformedXpak("key %i, tried reading data offset/len but hit EOF" % (len(keys_dict) + 1))
			keys_dict[key] = (data_start + offset, data_len)
			index_len -= (key_len + 12) # 12 for key_len, offset, data_len longs

		self._keys_dict = keys_dict
		
	def _check_magic(self, fd):
		fd.seek(-16, 2)
		try:
			pre, size, post = struct.unpack(self.trailer_parser, fd.read(self.trailer_size))
			if pre != self.trailer_pre_magic or post != self.trailer_post_magic:
				raise MalformedXpak("not an xpak segment, trailer didn't match: %r" % fd)
		except struct.error:
			raise MalformedXpak("not an xpak segment, failed parsing trailer: %r" % fd)

		# this is a bit daft, but the format seems to intentionally have an off by 8 in the offset address.
		# presumably cause the header was added after the fact, either way we go +8 to check the header magic.
		fd.seek(-(size + 8), 2)
		self.xpak_start = fd.tell()
		try:
			pre, index_len, data_len = struct.unpack(self.header_parser, fd.read(self.header_size))
			if pre != self.header_pre_magic:
				raise MalformedXpak("not an xpak segment, header didn't match: %r" % fd)
		except struct.error:
			raise MalformedXpak("not an xpak segment, failed parsing header: %r" % fd)

		return self.xpak_start + self.header_size, index_len, data_len

	def keys(self):
		return list(self.iterkeys())
	
	def values(self):
		return list(self.itervalues())
	
	def items(self):
		return list(self.iteritems())
	
	def __len__(self):
		return len(self._keys_dict)
	
	def __contains__(self, key):
		return key in self._keys_dict
	
	def __nonzero__(self):
		return bool(self._keys_dict)
	
	def __iter__(self):
		return iter(self._keys_dict)
	
	def iterkeys(self):
		return self._keys_dict.iterkeys()
	
	def itervalues(self):
		fd = self._fd
		return (self._get_data(fd, *v) for v in self._keys_dict.itervalues())
	
	def iteritems(self):
		# note that it's an OrderedDict, so this works.
		fd = self._fd
		return ((k, self._get_data(fd, *v)) for k, v in self._keys_dict.iteritems())

	def __getitem__(self, key):
		return self._get_data(self._fd, *self._keys_dict[key])

	def get(self, key, default=None):
		try:
			return self[key]
		except KeyError:
			return default

	def _get_data(self, fd, offset, data_len):
		# optimization for file objs; they cache tell position, but pass through all seek calls (nice, eh?)
		# so we rely on that for cutting down on uneeded seeks; userland comparison being far cheaper then an actual syscall seek
		if fd.tell() != offset:
			fd.seek(offset, 0)
		assert fd.tell() == offset
		r = fd.read(data_len)
		assert len(r) == data_len
		return r
