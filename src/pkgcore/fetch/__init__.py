"""
functionality related to downloading files
"""

__all__ = ("fetchable", "mirror", "default_mirror", "uri_list")

from itertools import zip_longest

from snakeoil.klass import generic_equality


class fetchable(metaclass=generic_equality):
    """class representing uri sources for a file and chksum information."""

    __slots__ = ("filename", "uri", "chksums")
    __attr_comparison__ = __slots__

    def __init__(self, filename, uri=None, chksums=None):
        """
        :param filename: filename...
        :param uri: either None (no uri),
            or a sequence of uri where the file is available
        :param chksums: either None (no chksum data),
            or a dict of chksum_type -> value for this file
        """
        self.uri = uri if uri is not None else ()
        self.chksums = chksums if chksums is not None else {}
        self.filename = filename

    def __str__(self):
        chksums = ', '.join(self.chksums)
        return f'({self.filename!r}, {self.uri!r}, {chksums})'

    def __repr__(self):
        return "<%s filename=%r uri=%r chksums=%r @%#8x>" % (
            self.__class__.__name__, self.filename, self.uri, self.chksums,
            id(self))

    def __lt__(self, other):
        return self.filename < other.filename

    def __hash__(self):
        return hash((self.filename, self.uri))

    @property
    def upstream(self):
        """Return a new fetchable with all mirror URIs removed."""
        uri_list = self.uri.remove_mirrors()
        return self.__class__(self.filename, uri=uri_list, chksums=self.chksums)


class mirror(metaclass=generic_equality):
    """uri source representing a mirror tier"""

    __attr_comparison__ = ('mirror_name', 'mirrors')

    __slots__ = ("mirrors", "mirror_name")

    def __init__(self, mirrors, mirror_name):
        """
        :param mirrors: list of hosts that comprise this mirror tier
        :param mirror_name: name of the mirror tier
        """

        if not isinstance(mirrors, tuple):
            mirrors = tuple(mirrors)
        self.mirrors = mirrors
        self.mirror_name = mirror_name

    def __iter__(self):
        return iter(self.mirrors)

    def __str__(self):
        return f"mirror://{self.mirror_name}"

    def __len__(self):
        return len(self.mirrors)

    def __bool__(self):
        return bool(self.mirrors)

    def __getitem__(self, idx):
        return self.mirrors[idx]

    def __repr__(self):
        return f"<{self.__class__} mirror tier={self.mirror_name!r}>"


class unknown_mirror(mirror):
    """Unknown mirror tier."""

    __slots__ = ()

    def __init__(self, mirror_name):
        super().__init__(mirrors=(), mirror_name=mirror_name)


class default_mirror(mirror):

    __slots__ = ()


class uri_list:

    __slots__ = ("_uri_source", "filename", "__weakref__")

    def __init__(self, filename):
        self._uri_source = []
        self.filename = filename

    def add_mirror(self, mirror_inst, sub_uri=None):
        if not isinstance(mirror_inst, mirror):
            raise TypeError("mirror must be a pkgcore.fetch.mirror instance")
        if sub_uri is not None:
            self._uri_source.append((mirror_inst, sub_uri.lstrip('/')))
        else:
            self._uri_source.append(mirror_inst)

    def remove_mirrors(self):
        """Return a new URI source list after dropping all mirror-based URIs."""
        uri_list = self.__class__(self.filename)
        uri_list._uri_source = tuple(x for x in self._uri_source if not isinstance(x, mirror))
        return uri_list

    def add_uri(self, uri):
        self._uri_source.append(uri)

    def finalize(self):
        self._uri_source = tuple(self._uri_source)

    def __iter__(self):
        fname = self.filename
        i = 0
        while i < len(self._uri_source):
            entry = self._uri_source[i]
            if isinstance(entry, str):
                yield entry
            elif isinstance(entry, tuple):
                # TODO: rewrite mirror handling to do this more transparently
                # collect all mirrors at the same priority
                mirrored = []
                while True:
                    m, sub_uri = entry
                    uris = (f"{base_uri.rstrip('/')}/{sub_uri}" for base_uri in m)
                    mirrored.append(uris)
                    try:
                        entry = self._uri_source[i + 1]
                    except IndexError:
                        break
                    if not isinstance(entry, tuple):
                        break
                    i += 1

                # iterate between different mirror groups
                for mirrored_uris in zip_longest(*mirrored):
                    yield from filter(None, mirrored_uris)
            else:
                for base_uri in entry:
                    yield f"{base_uri.rstrip('/')}/{fname}"
            i += 1

    def __str__(self):
        uris = ', '.join(str(x) for x in self._uri_source)
        return f"file: {self.filename}, uri: {uris}"

    def __bool__(self):
        # implemented this way on the off chance an empty sublist is handed in
        for entry in self:
            return True
        return False

    def __len__(self):
        # we do it this way since each item may be a sublist, and to reuse
        # __iter__
        count = 0
        for entry in self:
            count += 1
        return count

    def visit_mirrors(self, invert=False, treat_default_as_mirror=True):
        def is_mirror(item):
            return isinstance(item, mirror) and \
                treat_default_as_mirror == isinstance(item, default_mirror)
        for item in self._uri_source:
            if isinstance(item, tuple):
                if invert != is_mirror(item[0]):
                    yield item
            elif invert != is_mirror(item):
                yield item
