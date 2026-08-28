import bz2
import tarfile

import pytest
from snakeoil.data_source import data_source

from pkgcore.fs import contents, tar
from pkgcore.fs.fs import fsDir, fsFile, fsSymlink


def mk_file(location, data=b"", **kwds):
    kwds.setdefault("mode", 0o644)
    kwds.setdefault("uid", 0)
    kwds.setdefault("gid", 0)
    kwds.setdefault("mtime", 0)
    return fsFile(
        location, chksums={"size": len(data)}, data=data_source(data), **kwds
    )


class TestGenerateContents:
    def test_empty_archive(self, tmp_path):
        # a tarball whose decompressed payload is empty is not an error; it's an
        # empty contents set.  tarfile raises ReadError('empty file') for it.
        path = tmp_path / "empty.tar.bz2"
        path.write_bytes(bz2.compress(b""))
        assert not tar.generate_contents(str(path))

    def test_corrupt_archive(self, tmp_path):
        path = tmp_path / "corrupt.tar.bz2"
        path.write_bytes(bz2.compress(b"this is not a tar archive"))
        with pytest.raises(tarfile.ReadError):
            tar.generate_contents(str(path))

    def test_roundtrip(self, tmp_path):
        path = str(tmp_path / "test.tar.bz2")
        cset = contents.contentsSet(
            [
                fsDir("/usr", mode=0o755, uid=0, gid=0, mtime=0),
                mk_file("/usr/foo", b"hello", dev=1, inode=10),
                mk_file("/usr/hard", b"hello", dev=1, inode=10),
                fsSymlink("/usr/link", "foo", mode=0o777, uid=0, gid=0, mtime=0),
            ]
        )
        tar.write_set(cset, path)

        new_cset = tar.generate_contents(path)
        assert sorted(x.location for x in new_cset) == [
            "/usr",
            "/usr/foo",
            "/usr/hard",
            "/usr/link",
        ]

        regular = new_cset["/usr/foo"]
        assert regular.data.bytes_fileobj().read() == b"hello"
        # the hardlink resolves back to the target's inode
        assert new_cset["/usr/hard"].inode == regular.inode
