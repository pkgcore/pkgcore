import pytest

from pkgcore.fs import fs
from snakeoil.chksum import get_chksums
from snakeoil.data_source import data_source
from snakeoil.osutils import normpath, pjoin


class base:

    kls = None

    def make_obj(self, location="/tmp/foo", **kwds):
        kwds.setdefault("strict", False)
        return self.kls(location, **kwds)

    def test_basename(self):
        assert self.make_obj(location='/asdf').basename == 'asdf'
        assert self.make_obj(location='/a/b').basename == 'b'

    def test_dirname(self):
        assert self.make_obj(location='/asdf').dirname == '/'
        assert self.make_obj(location='/a/b').dirname == '/a'

    @pytest.mark.parametrize("loc", ('/tmp/a', '/tmp//a', '/tmp//', '/tmp/a/..'))
    def test_location_normalization(self, loc):
        assert self.make_obj(location=loc).location == normpath(loc)

    def test_change_attributes(self):
        # simple test...
        o = self.make_obj("/foon")
        assert o != o.change_attributes(location="/nanners")

    def test_init(self):
        mkobj = self.make_obj
        o = mkobj("/tmp/foo")
        assert o.location == "/tmp/foo"
        assert mkobj(mtime=100).mtime == 100
        assert mkobj(mode=0o660).mode == 0o660
        # ensure the highband stays in..
        assert mkobj(mode=0o42660).mode == 0o42660
        assert mkobj(uid=0).uid == 0
        assert mkobj(gid=0).gid == 0

    def test_hash(self):
        # might seem odd, but done this way to avoid the any potential
        # false positives from str's hash returning the same
        d = {self.make_obj("/tmp/foo"): None}
        # ensure it's accessible without a KeyError
        d[self.make_obj("/tmp/foo")]

    def test_eq(self):
        o = self.make_obj("/tmp/foo")
        assert o == self.make_obj("/tmp/foo")
        assert o != self.make_obj("/tmp/foo2")

    def test_setattr(self):
        o = self.make_obj()
        for attr in o.__attrs__:
            with pytest.raises(AttributeError):
                setattr(o, attr, "monkies")

    def test_realpath(self, tmp_path):
        # just to be safe, since this could trash some tests.
        (tmp_path / "test1").mkdir()
        obj = self.make_obj(location=str(tmp_path / "test1" / "foon"))
        assert obj is obj.realpath()

        (tmp_path / "test2").symlink_to(tmp_path / "test1")
        obj = self.make_obj(location=str(tmp_path / "test2" / "foon"))
        new_obj = obj.realpath()
        assert obj is not new_obj
        assert new_obj.location == str(tmp_path / "test1" / "foon")

        (tmp_path / "nonexistent").symlink_to(tmp_path / "test3")
        obj = self.make_obj(str(tmp_path / "nonexistent" / "foon"))
        # path is incomplete; should still realpath it.
        new_obj = obj.realpath()
        assert obj is not new_obj
        assert new_obj.location == str(tmp_path / "test3" / "foon")

    def test_default_attrs(self):
        assert self.make_obj(location="/adsf").mode is None
        class tmp(self.kls):
            __default_attrs__ = self.kls.__default_attrs__.copy()
            __default_attrs__['tmp'] = lambda self2:getattr(self2, 'a', 1)
            __attrs__ = self.kls.__attrs__ + ('tmp',)
            __slots__ = ('a', 'tmp')
        try:
            self.kls = tmp
            assert self.make_obj('/adsf', strict=False).tmp == 1
            t = self.make_obj('/asdf', a='foon', strict=False)
            assert t.tmp == "foon"
        finally:
            del self.kls


class Test_fsFile(base):

    kls = fs.fsFile

    def test_init(self):
        base.test_init(self)
        o = self.make_obj(__file__)
        with open(__file__) as f:
            raw_data = f.read()
        assert o.data.text_fileobj().read() == raw_data

        o = self.make_obj("/bin/this-file-should-not-exist-nor-be-read",
            data=data_source(raw_data))
        assert o.data.text_fileobj().read() == raw_data
        keys = list(o.chksums.keys())
        assert [o.chksums[x] for x in keys] == list(get_chksums(data_source(raw_data), *keys))

        chksums = dict(iter(o.chksums.items()))
        assert set(self.make_obj(chksums=chksums).chksums.items()) == set(chksums.items())

    def test_chksum_regen(self):
        data_source = object()
        obj = self.make_obj(__file__)
        assert obj.chksums is obj.change_attributes(location="/tpp").chksums
        chksums1 = obj.chksums
        assert chksums1 is not obj.change_attributes(data=data_source).chksums

        assert chksums1 is obj.change_attributes(data=data_source, chksums=obj.chksums).chksums

        obj2 = self.make_obj(__file__, chksums={1:2})
        assert obj2.chksums is obj2.change_attributes(data=data_source).chksums


class Test_fsLink(base):
    kls = fs.fsLink

    def make_obj(self, location="/tmp/foo", **kwds):
        target = kwds.pop("target", pjoin(location, "target"))
        kwds.setdefault("strict", False)
        return self.kls(location, target, **kwds)

    def test_init(self):
        base.test_init(self)
        assert self.make_obj(target="k9").target == "k9"
        assert self.make_obj(target="../foon").target == "../foon"

    def test_resolved_target(self):
        assert self.make_obj(location="/tmp/foon", target="dar").resolved_target == "/tmp/dar"
        assert self.make_obj(location="/tmp/foon", target="/dar").resolved_target == "/dar"

    def test_cmp(self):
        obj1 = self.make_obj(
            location='/usr/lib64/opengl/nvidia/lib/libnvidia-tls.so.1',
            target='../tls/libnvidia-tls.so.1')
        obj2 = self.make_obj(
            location='/usr/lib32/opengl/nvidia/lib/libGL.s',
            target='libGL.so.173.14.09')
        assert obj1 > obj2
        assert obj2 < obj1


class Test_fsDev(base):
    kls = fs.fsDev

    def test_init(self):
        base.test_init(self)
        mkobj = self.make_obj
        with pytest.raises(TypeError):
            mkobj(major=-1, strict=True)
        with pytest.raises(TypeError):
            mkobj(minor=-1, strict=True)
        assert mkobj(major=1).major == 1
        assert mkobj(minor=1).minor == 1


class Test_fsFifo(base):
    kls = fs.fsFifo


class Test_fsDir(base):
    kls = fs.fsDir


def test_is_funcs():
    # verify it intercepts the missing attr
    assert not fs.isdir(object())
    assert not fs.isreg(object())
    assert not fs.isfifo(object())

    assert fs.isdir(fs.fsDir('/tmp', strict=False))
    assert not fs.isreg(fs.fsDir('/tmp', strict=False))
    assert fs.isreg(fs.fsFile('/tmp', strict=False))
