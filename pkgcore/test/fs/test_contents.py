# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.fs import fs, contents
from pkgcore.util.currying import post_curry

import os


class TestContentsSet(TestCase):

    def __init__(self, *a, **kw):
        TestCase.__init__(self, *a, **kw)
        self.files = [fs.fsFile(x, strict=False) for x in [
                "/etc/blah", "/etc/foo", "/etc/dar", "/tmp/dar",
                "/tmp/blah/foo/long/ass/file/name/but/not/that/bad/really"]]
        self.dirs = [fs.fsDir(x, strict=False) for x in [
                "/tmp", "/blah", "/tmp/dar", "/usr/", "/usr/bin"]]
        self.links = [fs.fsLink(x, os.path.dirname(x), strict=False) for x in
            ["/tmp/foo", "/usr/X11R6/lib", "/nagga/noo"]]
        self.devs = [fs.fsDev(x, strict=False) for x in
            [os.path.join("dev", y) for y in (
                    "sda1", "hda", "hda2", "disks/ide1")]]
        self.fifos = [fs.fsFifo(x, strict=False) for x in
            [os.path.join("tmp", y) for y in ("dar", "boo", "bah")]]
        self.all = self.dirs + self.links + self.devs + self.fifos

    def test_init(self):
        self.assertEqual(len(self.all), len(contents.contentsSet(self.all)))
        self.assertRaises(TypeError, contents.contentsSet, self.all + [1])
        contents.contentsSet(self.all)
        contents.contentsSet(self.all, mutable=True)
        # test to ensure no one screwed up the optional initials
        # making it mandatory
        self.assertEqual(len(contents.contentsSet()), 0)

    def test_add(self):
        cs = contents.contentsSet(self.files + self.dirs, mutable=True)
        map(cs.add, self.links)
        for x in self.links:
            self.assertIn(x, cs)
        self.assertEqual(
            len(cs),
            len(set(x.location for x in self.files + self.dirs + self.links)))
        self.assertRaises(AttributeError,
            lambda:contents.contentsSet(mutable=False).add(self.devs[0]))
        self.assertRaises(TypeError, cs.add, 1)
        self.assertRaises(TypeError, cs.add, self.fifos)

    def test_remove(self):
        self.assertRaises(AttributeError,
            contents.contentsSet(mutable=False).remove, self.devs[0])
        self.assertRaises(AttributeError,
            contents.contentsSet(mutable=False).remove, 1)
        cs = contents.contentsSet(self.all, mutable=True)
        map(cs.remove, self.all)
        cs = contents.contentsSet(self.all, mutable=True)
        map(cs.remove, (x.location for x in self.all))
        self.assertEqual(len(cs), 0)
        self.assertRaises(KeyError, cs.remove, self.all[0])

    def test_contains(self):
        cs = contents.contentsSet(mutable=True)
        for x in [y[0] for y in [
                self.files, self.dirs, self.links, self.devs, self.fifos]]:
            self.assertFalse(x in cs)
            self.assertFalse(x.location in cs)
            cs.add(x)
            self.assertTrue(x in cs)
            self.assertTrue(x.location in cs)
            cs.remove(x)

    def test_clear(self):
        cs = contents.contentsSet(self.all, mutable=True)
        self.assertTrue(len(cs))
        cs.clear()
        self.assertEqual(len(cs), 0)

    def test_len(self):
        self.assertEqual(len(contents.contentsSet(self.all)), len(self.all))

    def iterobj(self, name, obj_class=None, forced_name=None):
        s = set(getattr(self, name))
        cs = contents.contentsSet(s)
        if forced_name is None:
            forced_name = "iter"+name

        s2 = set(getattr(cs, forced_name)())
        if obj_class is not None:
            map(post_curry(self.assertTrue, obj_class), s2)
        self.assertEqual(s, s2)

        if forced_name == "__iter__":
            return

        # inversion tests now.
        s3 = set(getattr(cs, forced_name)(invert=True))
        if obj_class is not None:
            map(post_curry(self.assertFalse, obj_class), s3)

        self.assertEqual(s.symmetric_difference(s2), s3)


    def listobj(self, name, obj_class=None):
        valid_list = getattr(self, name)
        cs = contents.contentsSet(valid_list)
        test_list = getattr(cs, name)()
        if obj_class is not None:
            for x in test_list:
                self.assertInstance(x, obj_class)
        self.assertEqual(set(test_list), set(valid_list))

    test_iterfiles = post_curry(iterobj, "files", fs.fsFile)
    test_files = post_curry(listobj, "files", fs.fsFile)

    test_iterdirs = post_curry(iterobj, "dirs", fs.fsDir)
    test_dirs = post_curry(listobj, "dirs", fs.fsDir)

    test_iterlinks = post_curry(iterobj, "links", fs.fsLink)
    test_links = post_curry(listobj, "links", fs.fsLink)

    test_iterdevs = post_curry(iterobj, "devs", fs.fsDev)
    test_devs = post_curry(listobj, "devs", fs.fsDev)

    test_iterfifos = post_curry(iterobj, "fifos", fs.fsFifo)
    test_fifos = post_curry(listobj, "fifos", fs.fsFifo)

    test_iter = post_curry(iterobj, "all", forced_name="__iter__")

    def test_check_instance(self):
        for x in [y[0] for y in [
                self.files, self.dirs, self.links, self.devs, self.fifos]]:
            self.assertEqual((x.location, x), tuple(contents.check_instance(x)))
        self.assertRaises(TypeError, contents.check_instance, 1)

    def check_set_op(self, name, ret, source=None):
        if source is None:
            source = [[fs.fsDir("/tmp", strict=False)],
                      [fs.fsFile("/tmp", strict=False)]]

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(c2)
            c3 = c1
        else:
            c3 = getattr(c1, name)(c2)
        self.assertEqual(
            set(ret),
            set(x.location for x in c3))

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(iter(c2))
            c3 = c1
        else:
            c3 = getattr(c1, name)(iter(c2))
        self.assertEqual(
            set(ret),
            set(x.location for x in c3))

    test_intersection = post_curry(check_set_op, "intersection", ["/tmp"])
    test_intersection_update = post_curry(check_set_op,
        "intersection_update", ["/tmp"])

    test_difference = post_curry(check_set_op, "difference", [])
    test_difference_update = post_curry(check_set_op,
        "difference_update", [])

    test_symmetric_difference1 = post_curry(
        check_set_op, "symmetric_difference", [])
    test_symmetric_difference1_update = post_curry(
        check_set_op, "symmetric_difference_update", [])

    fstrings = ("/a", "/b", "/c", "/d")
    f = [fs.fsFile(x, strict=False) for x in fstrings]

    test_union1 = post_curry(check_set_op, "union", ["/tmp"])
    test_union2 = post_curry(check_set_op, "union", fstrings, [f[:2], f[2:]])

    test_symmetric_difference2 = post_curry(
        check_set_op, "symmetric_difference", fstrings, [f[:2], f[2:]])
    test_symmetric_difference2_update = post_curry(
        check_set_op, "symmetric_difference", fstrings, [f[:2], f[2:]])

    del f, fstrings
