import os
from pathlib import Path

import pytest

from pkgcore.fs import contents, fs, livefs, ops
from snakeoil.data_source import local_source


def verify(obj, kwds):
    stat = os.stat(obj.location)
    for attr, keyword in (("st_mtime", "mtime"),
                          ("st_gid", "gid"),
                          ("st_uid", "uid")):
        if keyword in kwds:
            assert getattr(stat, attr) == kwds[keyword], f"testing {keyword}"
    if "mode" in kwds:
        assert (stat.st_mode & 0o4777) == kwds["mode"]


@pytest.mark.parametrize(("creator_func", "kls"), (
    pytest.param(os.mkdir, fs.fsDir, id="dir"),
    pytest.param(lambda s: open(s, "w").close(), fs.fsFile, id="file"),
))
def test_default_ensure_perms(tmp_path, creator_func, kls):
    kwds = dict(mtime=0o1234, uid=os.getuid(), gid=os.getgid(),
                mode=0o775, dev=None, inode=None)
    o = kls(str(tmp_path / "blah"), **kwds)
    creator_func(o.location)
    assert ops.ensure_perms(o)
    verify(o, kwds)

    kwds["mode"] = 0o770
    o2 = kls(str(tmp_path / "blah"), **kwds)
    assert ops.ensure_perms(o2)
    verify(o2, kwds)

    with pytest.raises(OSError):
        ops.ensure_perms(kls(str(tmp_path / "asdf"), **kwds))


def test_default_mkdir(tmp_path):
    o = fs.fsDir(str(tmp_path / "mkdir_test"), strict=False)
    assert ops.mkdir(o)
    old_umask = os.umask(0)
    try:
        assert (os.stat(o.location).st_mode & 0o4777) == (0o777 & ~old_umask)
    finally:
        os.umask(old_umask)
    os.rmdir(o.location)

    o = fs.fsDir(str(tmp_path / "mkdir_test2"), strict=False, mode=0o750)
    assert ops.mkdir(o)
    assert (os.stat(o.location).st_mode & 0o4777) == 0o750


class TestCopyFile:

    def test_it(self, tmp_path):
        content = "\n".join("asdf" for _ in range(10))
        (src := tmp_path / "copy_test_src").write_text(content)
        dest = tmp_path / "copy_test_dest"

        kwds = {"mtime":10321, "uid":os.getuid(), "gid":os.getgid(),
                "mode":0o664, "data":local_source(str(src)), "dev":None,
                "inode":None}
        o = fs.fsFile(str(dest), **kwds)
        assert ops.copyfile(o)
        assert dest.read_text() == content
        verify(o, kwds)

    def test_sym_perms(self, tmp_path):
        curgid = os.getgid()
        group = [x for x in os.getgroups() if x != curgid]
        if not group and os.getuid() != 0:
            pytest.skip(
                "requires root privs for this test, or for this user to"
                "belong to more then one group"
            )
        group = group[0]
        fp = str(tmp_path / "sym")
        o = fs.fsSymlink(fp, mtime=10321, uid=os.getuid(), gid=group,
            mode=0o664, target='target')
        assert ops.copyfile(o)
        assert os.lstat(fp).st_gid == group
        assert os.lstat(fp).st_uid == os.getuid()

    def test_puke_on_dirs(self, tmp_path: Path):
        path = str(tmp_path / "puke_dir")
        with pytest.raises(TypeError):
            ops.copyfile(fs.fsDir(path, strict=False))
        os.mkdir(path)
        fp = str(tmp_path / "foon")
        open(fp, "w").close()
        f = livefs.gen_obj(fp)
        with pytest.raises(TypeError):
            livefs.gen_obj(fp).change_attributes(location=path)()

        # test sym over a directory.
        f = fs.fsSymlink(path, fp, mode=0o644, mtime=0, uid=os.getuid(), gid=os.getgid())
        with pytest.raises(TypeError):
            ops.copyfile(f)
        os.unlink(fp)
        os.mkdir(fp)
        with pytest.raises(ops.CannotOverwrite):
            ops.copyfile(f)


class ContentsMixin:

    entries_norm1 = {
        "file1": ["reg"],
        "dir": ["dir"],
        "dir/subdir": ["dir"],
        "dir/file2": ["reg"],
        "ldir": ["sym", "dir/subdir"],
        "dir/lfile": ["sym", "../file1"],
    }

    entries_rec1 = {
        "dir": ["dir"],
        "dir/link": ["sym", "../dir"],
    }

    def generate_tree(self, base, entries):
        base.mkdir()
        s_ents = [(base / k, entries[k]) for k in sorted(entries)]
        for k, v in s_ents:
            if v[0] == "dir":
                k.mkdir()
        for k, v in s_ents:
            if v[0] == "dir":
                pass
            elif v[0] == "reg":
                k.touch()
            elif v[0] == "sym":
                k.symlink_to(v[1])
            else:
                pytest.fail(f"generate_tree doesn't support type {v!r} yet: k {k!r}")
        return str(base)


class TestMergeContents(ContentsMixin):

    @pytest.fixture
    def generic_merge_bits(self, request, tmp_path):
        entries = getattr(self, request.param)
        assert isinstance(entries, dict)
        src = self.generate_tree(tmp_path / "src", entries)
        cset = livefs.scan(src, offset=src)
        (dest := tmp_path / "dest").mkdir()
        dest = str(dest)
        assert ops.merge_contents(cset, offset=dest)
        assert livefs.scan(src, offset=src) == livefs.scan(dest, offset=dest)
        return src, dest, cset

    @pytest.mark.parametrize("generic_merge_bits", ("entries_norm1", "entries_rec1"), indirect=True)
    def test_callback(self, generic_merge_bits):
        src, dest, cset = generic_merge_bits
        new_cset = contents.contentsSet(contents.offset_rewriter(dest, cset))
        s = set(new_cset)
        ops.merge_contents(cset, offset=dest, callback=s.remove)
        assert not s

    def test_dangling_symlink(self, tmp_path):
        src = self.generate_tree(tmp_path / "src", {"dir": ["dir"]})
        cset = livefs.scan(src, offset=src)
        (dest := tmp_path / "dest").mkdir()
        (dest / "dir").symlink_to(dest / "dest")
        assert ops.merge_contents(cset, offset=str(dest))
        assert cset == livefs.scan(src, offset=str(dest))

    @pytest.mark.parametrize("generic_merge_bits", ("entries_norm1", ), indirect=True)
    def test_exact_overwrite(self, generic_merge_bits):
        src, dest, cset = generic_merge_bits
        assert ops.merge_contents(cset, offset=dest)

    def test_sym_over_dir(self, tmp_path):
        (path := tmp_path / "sym").mkdir()
        fp = tmp_path / "trg"
        # test sym over a directory.
        f = fs.fsSymlink(str(path), str(fp), mode=0o644, mtime=0,
            uid=os.getuid(), gid=os.getgid())
        cset = contents.contentsSet([f])
        with pytest.raises(ops.FailedCopy):
            ops.merge_contents(cset)
        assert fs.isdir(livefs.gen_obj(str(path)))
        fp.mkdir()
        ops.merge_contents(cset)

    def test_dir_over_file(self, tmp_path):
        # according to the spec, dirs can't be merged over files that
        # aren't dirs or symlinks to dirs
        (path := tmp_path / "file2dir").touch()
        d = fs.fsDir(str(path), mode=0o755, mtime=0, uid=os.getuid(), gid=os.getgid())
        cset = contents.contentsSet([d])
        with pytest.raises(ops.CannotOverwrite):
            ops.merge_contents(cset)


class TestUnmergeContents(ContentsMixin):

    @pytest.fixture
    def generic_unmerge_bits(self, request, tmp_path):
        entries = getattr(self, request.param)
        assert isinstance(entries, dict)
        img = self.generate_tree(tmp_path / "img", entries)
        cset = livefs.scan(img, offset=img)
        return img, cset

    @pytest.mark.parametrize("generic_unmerge_bits", ("entries_norm1", "entries_rec1"), indirect=True)
    def test_callback(self, generic_unmerge_bits):
        img, cset = generic_unmerge_bits
        s = set(contents.offset_rewriter(img, cset))
        ops.unmerge_contents(cset, offset=img, callback=s.remove)
        assert not s

    @pytest.mark.parametrize("generic_unmerge_bits", ("entries_norm1", ), indirect=True)
    def test_empty_removal(self, tmp_path, generic_unmerge_bits):
        img, cset = generic_unmerge_bits
        assert ops.unmerge_contents(cset, offset=str(tmp_path / "dest"))

    @pytest.mark.parametrize("generic_unmerge_bits", ("entries_norm1", ), indirect=True)
    def test_exact_removal(self, generic_unmerge_bits):
        img, cset = generic_unmerge_bits
        assert ops.unmerge_contents(cset, offset=img)
        assert not livefs.scan(img, offset=img)

    @pytest.mark.parametrize("generic_unmerge_bits", ("entries_norm1", ), indirect=True)
    def test_lingering_file(self, generic_unmerge_bits):
        img, cset = generic_unmerge_bits
        dirs = [k for k, v in self.entries_norm1.items() if v[0] == "dir"]
        (fp := Path(img) / dirs[0] / "linger").touch()
        assert ops.unmerge_contents(cset, offset=img)
        assert fp.exists()
