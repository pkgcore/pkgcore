# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore import fetch

from pkgcore.test import TestCase


class TestFetchable(TestCase):

    def test_init(self):
        o = fetch.fetchable("dar", uri=["asdf"], chksums={"asdf":1})
        self.assertEqual(o.filename, "dar")
        self.assertEqual(o.uri, ["asdf"])
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


class TestMirror(TestCase):

    kls = fetch.mirror

    default_mirrors = ["http://foon", "ftp://spoon"]
    def setUp(self):
        self.mirror = self.kls(self.default_mirrors, "fork")

    def test_init(self):
        self.assertEqual(self.mirror.mirror_name, "fork")
        # explicit test should any tuple like sequence show up
        self.assertTrue(isinstance(self.mirror.mirrors, tuple))
        self.assertEqual(self.mirror.mirrors, tuple(self.default_mirrors))

    def test_iter(self):
        self.assertEqual(list(self.mirror), self.default_mirrors)

    def test_len(self):
        self.assertEqual(len(self.mirror), len(self.default_mirrors))

    def test_getitem(self):
        self.assertEqual(self.mirror[1], self.default_mirrors[1])


class TestDefaultMirror(TestMirror):

    kls = fetch.default_mirror


class Test_uri_list(TestCase):

    def setUp(self):
        self.uril = fetch.uri_list("cows")

    def test_mirrors(self):
        self.assertRaises(TypeError, self.uril.add_mirror, "cows")
        mirror = fetch.mirror(["me", "WI"], "asdf")
        self.uril.add_mirror(mirror)
        self.assertEqual(list(self.uril), ["me/cows", "WI/cows"])
        self.uril.add_mirror(mirror, "foon/boon")
        self.assertEqual(list(self.uril),
            ["me/cows", "WI/cows", "me/foon/boon", "WI/foon/boon"])

    def test_uris(self):
        self.uril.add_uri("blar")
        self.assertEqual(list(self.uril), ["blar"])

    def test_combined(self):
        l = ["blarn", "me/cows", "WI/cows", "madison",
            "belleville/cows", "verona/cows"]
        self.uril.add_uri("blarn")
        self.uril.add_mirror(fetch.mirror(["me", "WI"], "asdf"))
        self.uril.add_uri("madison")
        self.uril.add_mirror(fetch.default_mirror(
            ["belleville", "verona"], "foon"))
        self.assertEqual(list(self.uril), l)
