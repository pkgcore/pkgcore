import pytest

from pkgcore import fetch
from snakeoil.sequences import iflatten_instance


def assert_uri(obj, uri):
    uri = list(uri)
    assert list(iflatten_instance(obj)) == uri
    assert bool(uri) == bool(obj)


class TestFetchable:

    def test_init(self):
        o = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        assert o.filename == "dar"
        assert_uri(o.uri, ["asdf"])
        assert o.chksums == {"asdf":1}

    def test_eq_ne(self):
        o1 = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        assert o1 == o1
        o2 = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        assert o1 == o2
        assert o1 != fetch.fetchable("dar1", uri=["asdf"], chksums={"asdf":1})
        assert o1 != fetch.fetchable("dar", uri=["asdf1"], chksums={"asdf":1})
        assert o1 != fetch.fetchable("dar", uri=["asdf1"], chksums={"asdf":1, "foon":1})


class TestMirror:

    kls = fetch.mirror
    default_mirrors = ["http://foon", "ftp://spoon"]

    @pytest.fixture
    def mirror(self):
        return self.kls(self.default_mirrors, "fork")

    def test_init(self, mirror):
        assert mirror.mirror_name == "fork"
        # explicit test should any tuple like sequence show up
        assert isinstance(mirror.mirrors, tuple)
        assert mirror.mirrors == tuple(self.default_mirrors)

    def test_iter(self, mirror):
        assert list(mirror) == self.default_mirrors

    def test_len(self, mirror):
        assert len(mirror) == len(self.default_mirrors)

    def test_getitem(self, mirror):
        assert mirror[1] == self.default_mirrors[1]

    def test_eq_ne(self, mirror):
        assert mirror == self.kls(self.default_mirrors, 'fork')
        assert mirror != self.kls(self.default_mirrors + ['http://fark'], 'fork')


class TestDefaultMirror(TestMirror):

    kls = fetch.default_mirror


class Test_uri_list:

    @pytest.fixture
    def uril(self):
        return fetch.uri_list("cows")

    @staticmethod
    def mk_uri_list(*iterable, **kwds):
        filename = kwds.get("filename", "asdf")
        obj = fetch.uri_list(filename)
        for x in iterable:
            if isinstance(x, fetch.mirror):
                obj.add_mirror(x)
            else:
                obj.add_uri(x)
        return obj

    def test_mirrors(self, uril):
        with pytest.raises(TypeError):
            uril.add_mirror("cows")
        mirror = fetch.mirror(["me", "WI"], "asdf")
        uril.add_mirror(mirror)
        assert list(uril) == ["me/cows", "WI/cows"]
        uril.add_mirror(mirror, "foon/boon")
        assert_uri(uril,
            ["me/cows", "WI/cows", "me/foon/boon", "WI/foon/boon"])

    def test_uris(self, uril):
        uril.add_uri("blar")
        assert_uri(uril, ["blar"])

    def test_combined(self, uril):
        l = ["blarn", "me/cows", "WI/cows", "madison",
            "belleville/cows", "verona/cows"]
        uril.add_uri("blarn")
        uril.add_mirror(fetch.mirror(["me", "WI"], "asdf"))
        uril.add_uri("madison")
        uril.add_mirror(fetch.default_mirror(
            ["belleville", "verona"], "foon"))
        assert_uri(uril, l)

    def test_nonzero(self):
        assert self.mk_uri_list("asdf")
        assert not self.mk_uri_list()
        assert not self.mk_uri_list(fetch.mirror((), "mirror"))

    def test_len(self):
        assert len(self.mk_uri_list()) == 0
        assert len(self.mk_uri_list("fdas")) == 1
        assert len(self.mk_uri_list(fetch.mirror((), "mirror"))) == 0
        assert len(self.mk_uri_list(fetch.mirror(("asdf",), "mirror"))) == 1
