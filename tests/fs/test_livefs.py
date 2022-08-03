import os
from pathlib import Path

import pytest

from pkgcore.fs import fs, livefs
from pkgcore.fs.contents import contentsSet


class TestFsObjs:

    def check_attrs(self, obj, path, offset=None):
        if offset is None:
            st = path.lstat()
        else:
            st = (offset / path).lstat()
        if offset is not None:
            assert offset.is_absolute(), f"path must be absolute, got {path!r}"
        assert (obj.mode & 0o7777) == (st.st_mode & 0o7777)
        assert obj.uid == st.st_uid
        assert obj.gid == st.st_gid
        if fs.isreg(obj):
            if offset is None:
                assert obj.data.path == str(path)
            else:
                assert obj.data.path == str(offset / path)

    def test_data_source(self):
        o = livefs.gen_obj("/tmp/etc/passwd", real_location="/etc/passwd")
        assert o.location, "/tmp/etc/passwd"
        assert o.data.path, "/etc/passwd"
        with open("/etc/passwd", "rb") as f:
            assert o.data.bytes_fileobj().read(), f.read()

    def test_gen_obj_reg(self, tmp_path):
        (path := tmp_path / "reg_obj").touch()
        o = livefs.gen_obj(str(path))
        assert fs.isreg(o)
        self.check_attrs(o, path)
        o2 = livefs.gen_obj(str(path), inode=None)
        self.check_attrs(o, path)
        assert o.inode != o2.inode

    def test_gen_obj_dir(self, tmp_path):
        o = livefs.gen_obj(str(tmp_path))
        assert fs.isdir(o)
        self.check_attrs(o, tmp_path)

    def test_gen_obj_sym(self, tmp_path):
        (src := tmp_path / "s").touch()
        (link := tmp_path / "t").symlink_to(src)
        obj = livefs.gen_obj(str(link))
        assert isinstance(obj, fs.fsSymlink)
        self.check_attrs(obj, link)
        assert os.readlink(link) == obj.target

    def test_gen_obj_fifo(self, tmp_path):
        os.mkfifo(path := tmp_path / "fifo")
        o = livefs.gen_obj(str(path))
        self.check_attrs(o, path)

    def test_iterscan(self, tmp_path):
        (path := tmp_path / "iscan").mkdir()
        files = [path / x for x in ("tmp", "blah", "dar")]
        for x in files:
            x.touch()
        dirs = [path / x for x in ("a", "b", "c")]
        for x in dirs:
            x.mkdir()
        dirs.append(path)
        for obj in livefs.iter_scan(str(path)):
            assert isinstance(obj, fs.fsBase)
            if fs.isreg(obj):
                assert Path(obj.location) in files
            elif fs.isdir(obj):
                assert Path(obj.location) in dirs
            else:
                pytest.fail(f"unknown object popped up in testing dir, {obj!r}")
            self.check_attrs(obj, Path(obj.location))

        # do offset verification now.
        offset = path
        for obj in livefs.iter_scan(str(path), offset=str(offset)):
            self.check_attrs(obj, Path(obj.location).relative_to('/'), offset=offset)

        seen = []
        for obj in livefs.iter_scan(str(files[0])):
            self.check_attrs(obj, Path(obj.location))
            seen.append(obj.location)
        assert [str(files[0])] == sorted(seen)

    def test_sorted_scan(self, tmp_path):
        for x in ("tmp", "blah", "dar"):
            (tmp_path / x).touch()
        for x in ("a", "b", "c"):
            (tmp_path / x).mkdir()

        # regular directory scanning
        sorted_files = livefs.sorted_scan(str(tmp_path))
        assert sorted_files == [str(tmp_path / x) for x in ('blah', 'dar', 'tmp')]

        # nonexistent paths
        nonexistent_path = str(tmp_path / 'foobar')
        assert livefs.sorted_scan(nonexistent_path) == []
        assert livefs.sorted_scan(nonexistent_path, nonexistent=True) == [nonexistent_path]

    def test_sorted_scan_hidden(self, tmp_path):
        for x in (".tmp", "blah"):
            (tmp_path / x).touch()

        sorted_files = livefs.sorted_scan(str(tmp_path))
        assert [str(tmp_path / x) for x in ('.tmp', 'blah')] == sorted_files
        sorted_files = livefs.sorted_scan(str(tmp_path), hidden=False)
        assert [str(tmp_path / x) for x in ('blah', )] == sorted_files

    def test_sorted_scan_backup(self, tmp_path):
        for x in ("blah", "blah~"):
            (tmp_path / x).touch()

        sorted_files = livefs.sorted_scan(str(tmp_path))
        assert [str(tmp_path / x) for x in ("blah", "blah~")] == sorted_files
        sorted_files = livefs.sorted_scan(str(tmp_path), backup=False)
        assert [str(tmp_path / x) for x in ('blah', )] == sorted_files

    def test_relative_sym(self, tmp_path):
        (path := tmp_path / "relative-symlink-test").symlink_to("../sym1/blah")
        o = livefs.gen_obj(str(path))
        assert o.target == "../sym1/blah"

    def test_intersect(self, tmp_path):
        (tmp_path / 'reg').touch()
        cset = contentsSet([fs.fsFile('reg', strict=False)])
        cset = cset.insert_offset(str(tmp_path))
        assert contentsSet(livefs.intersect(cset)) == cset
        cset = contentsSet([fs.fsFile('reg/foon', strict=False),
            fs.fsFile('reg/dar', strict=False),
            fs.fsDir('reg/dir', strict=False)]).insert_offset(str(tmp_path))
        assert not list(livefs.intersect(cset))
        cset = contentsSet([fs.fsDir('reg', strict=False)])
        assert not list(livefs.intersect(cset))
