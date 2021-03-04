from snakeoil.sequences import iflatten_instance
from snakeoil.test import TestCase

from pkgcore import fetch


class base(TestCase):

    def assertUri(self, obj, uri):
        uri = list(uri)
        self.assertEqual(list(iflatten_instance(obj)), uri)
        if uri:
            self.assertTrue(obj)
        else:
            self.assertFalse(obj)


class TestFetchable(base):

    def test_init(self):
        o = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        self.assertEqual(o.filename, "dar")
        self.assertUri(o.uri, ["asdf"])
        self.assertEqual(o.chksums, {"asdf":1})

    def test_eq_ne(self):
        o1 = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        self.assertEqual(o1, o1)
        o2 = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        self.assertEqual(o1, o2)
        self.assertNotEqual(o1,
            fetch.fetchable("dar1", uri=["asdf"], chksums={"asdf":1}))
        self.assertNotEqual(o1,
            fetch.fetchable("dar", uri=["asdf1"], chksums={"asdf":1}))
        self.assertNotEqual(o1,
            fetch.fetchable("dar", uri=["asdf1"], chksums={"asdf":1, "foon":1}))


class TestMirror(base):

    kls = fetch.mirror

    default_mirrors = ["http://foon", "ftp://spoon"]
    def setUp(self):
        self.mirror = self.kls(self.default_mirrors, "fork")

    def test_init(self):
        self.assertEqual(self.mirror.mirror_name, "fork")
        # explicit test should any tuple like sequence show up
        self.assertInstance(self.mirror.mirrors, tuple)
        self.assertEqual(self.mirror.mirrors, tuple(self.default_mirrors))

    def test_iter(self):
        self.assertEqual(list(self.mirror), self.default_mirrors)

    def test_len(self):
        self.assertEqual(len(self.mirror), len(self.default_mirrors))

    def test_getitem(self):
        self.assertEqual(self.mirror[1], self.default_mirrors[1])

    def test_eq_ne(self):
        self.assertEqual(self.mirror, self.kls(self.default_mirrors, 'fork'))
        self.assertNotEqual(self.mirror,
            self.kls(self.default_mirrors + ['http://fark'], 'fork'))


class TestDefaultMirror(TestMirror):

    kls = fetch.default_mirror


class Test_uri_list(base):

    def setUp(self):
        self.uril = fetch.uri_list("cows")

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

    def test_mirrors(self):
        self.assertRaises(TypeError, self.uril.add_mirror, "cows")
        mirror = fetch.mirror(["me", "WI"], "asdf")
        self.uril.add_mirror(mirror)
        self.assertEqual(list(self.uril), ["me/cows", "WI/cows"])
        self.uril.add_mirror(mirror, "foon/boon")
        self.assertUri(self.uril,
            ["me/cows", "WI/cows", "me/foon/boon", "WI/foon/boon"])

    def test_uris(self):
        self.uril.add_uri("blar")
        self.assertUri(self.uril, ["blar"])

    def test_combined(self):
        l = ["blarn", "me/cows", "WI/cows", "madison",
            "belleville/cows", "verona/cows"]
        self.uril.add_uri("blarn")
        self.uril.add_mirror(fetch.mirror(["me", "WI"], "asdf"))
        self.uril.add_uri("madison")
        self.uril.add_mirror(fetch.default_mirror(
            ["belleville", "verona"], "foon"))
        self.assertUri(self.uril, l)

    def test_nonzero(self):
        self.assertTrue(self.mk_uri_list("asdf"))
        self.assertFalse(self.mk_uri_list())
        self.assertFalse(self.mk_uri_list(fetch.mirror((), "mirror")))

    def test_len(self):
        self.assertLen(self.mk_uri_list(), 0)
        self.assertLen(self.mk_uri_list("fdas"), 1)
        self.assertLen(self.mk_uri_list(fetch.mirror((), "mirror")), 0)
        self.assertLen(self.mk_uri_list(fetch.mirror(("asdf",), "mirror")), 1)
