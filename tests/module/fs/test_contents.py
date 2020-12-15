import os
from functools import partial

from snakeoil.currying import post_curry
from snakeoil.osutils import pjoin
from snakeoil.test import TestCase

from pkgcore.fs import contents, fs

mk_file = partial(fs.fsFile, strict=False)
mk_dir  = partial(fs.fsDir, strict=False)
mk_link = partial(fs.fsLink, strict=False)
mk_dev  = partial(fs.fsDev, strict=False)
mk_fifo = partial(fs.fsFifo, strict=False)

for x in ("File", "Dir", "Link", "Dev", "Fifo"):
    globals()["mk_" + x.lower()] = partial(
        getattr(fs, f"fs{x}"), strict=False)
del x


class TestContentsSet(TestCase):

    locals().update((x, globals()[x]) for x in
        ("mk_file", "mk_dir", "mk_link", "mk_dev", "mk_fifo"))

    def __init__(self, *a, **kw):
        TestCase.__init__(self, *a, **kw)
        self.files = list(map(self.mk_file, ["/etc/blah", "/etc/foo", "/etc/dar",
             "/tmp/dar",
             "/tmp/blah/foo/long/ass/file/name/but/not/that/bad/really"]))
        self.dirs = list(map(self.mk_dir, ["/tmp", "/blah", "/tmp/dar",
            "/usr/", "/usr/bin"]))
        self.links = [fs.fsLink(x, os.path.dirname(x), strict=False) for x in
            ["/tmp/foo", "/usr/X11R6/lib", "/nagga/noo"]]
        self.devs = list(map(self.mk_dev,
            [pjoin("dev", x) for x in ["sda1", "hda", "hda2", "disks/ide1"]]))
        self.fifos = list(map(self.mk_fifo,
            [pjoin("tmp", y) for y in ("dar", "boo", "bah")]))
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
        for x in self.links:
            cs.add(x)
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
        for x in self.all:
            cs.remove(x)
        cs = contents.contentsSet(self.all, mutable=True)
        for location in (x.location for x in self.all):
            cs.remove(location)
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
            for x in s2:
                post_curry(self.assertTrue, obj_class)(x)
        self.assertEqual(s, s2)

        if forced_name == "__iter__":
            return

        # inversion tests now.
        s3 = set(getattr(cs, forced_name)(invert=True))
        if obj_class is not None:
            for x in s3:
                post_curry(self.assertFalse, obj_class)(x)

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
    f = list(map(mk_file, fstrings))

    test_union1 = post_curry(check_set_op, "union", ["/tmp"])
    test_union2 = post_curry(check_set_op, "union", fstrings, [f[:2], f[2:]])

    test_symmetric_difference2 = post_curry(
        check_set_op, "symmetric_difference", fstrings, [f[:2], f[2:]])
    test_symmetric_difference2_update = post_curry(
        check_set_op, "symmetric_difference", fstrings, [f[:2], f[2:]])

    del f, fstrings

    def check_complex_set_op(self, name, *test_cases):
        for required, data1, data2 in test_cases:
            cset1 = contents.contentsSet(data1)
            cset2 = contents.contentsSet(data2)
            f = getattr(cset1, name)
            got = f(cset2)
            self.assertEqual(
                got, required,
                msg=f"{name}: expected {required}, got {got}\ncset1={cset1!r}\ncset2={cset2!r}")

    test_issubset = post_curry(
        check_complex_set_op, "issubset",
            (True, [mk_file("/foon")], [mk_file("/foon")]),
            (False, [mk_file("/foon")], [mk_file("/dev")]),
            (False, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
            (True, [mk_file("/dev"), mk_file("/dar")],
                [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")])
        )


    test_issuperset = post_curry(
        check_complex_set_op, "issuperset",
            (True, [mk_file("/foon")], [mk_file("/foon")]),
            (False, [mk_file("/foon")], [mk_file("/dev")]),
            (True, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
            (False, [mk_file("/dev")], [mk_file("/dev"), mk_file("/dev2")])
        )


    test_isdisjoin = post_curry(
        check_complex_set_op, "isdisjoint",
            (False, [mk_file("/foon")], [mk_file("/foon")]),
            (True, [mk_file("/foon")], [mk_file("/dev")]),
            (False, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
            (False, [mk_file("/dev"), mk_file("/dar")],
                [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")]),
            (False, [mk_file("/dev"), mk_file("/dar")],
                [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")]),
            (True, [mk_file("/dev"), mk_file("/dar")],
                [mk_file("/dev2"), mk_file("/dar2"), mk_file("/asdf")]),
        )


    def test_child_nodes(self):
        self.assertEqual(sorted(['/usr', '/usr/bin', '/usr/foo']),
            sorted(x.location for x in contents.contentsSet(
                [self.mk_dir("/usr"), self.mk_dir("/usr/bin"),
                self.mk_file("/usr/foo")])))

    def test_map_directory_structure(self):
        old = contents.contentsSet([self.mk_dir("/dir"),
            self.mk_link("/sym", "dir")])
        new = contents.contentsSet([self.mk_file("/sym/a"),
            self.mk_dir("/sym")])
        # verify the machinery is working as expected.
        ret = new.map_directory_structure(old)
        self.assertEqual(sorted(ret), sorted([self.mk_dir("/dir"),
            self.mk_file("/dir/a")]))

        # test recursion next.
        old.add(self.mk_link("/dir/sym", "dir2"))
        old.add(self.mk_dir("/dir/dir2"))
        new.add(self.mk_file("/dir/sym/b"))
        new.add(self.mk_dir("/sym/sym"))

        ret = new.map_directory_structure(old)
        self.assertEqual(sorted(ret), sorted([self.mk_dir("/dir"),
            self.mk_file("/dir/a"), self.mk_dir("/dir/dir2"),
            self.mk_file("/dir/dir2/b")]))


    def test_add_missing_directories(self):
        src = [self.mk_file("/dir1/a"), self.mk_file("/dir2/dir3/b"),
            self.mk_dir("/dir1/dir4")]
        cs = contents.contentsSet(src)
        cs.add_missing_directories()
        self.assertEqual(sorted(x.location for x in cs),
            ['/dir1', '/dir1/a', '/dir1/dir4', '/dir2', '/dir2/dir3',
                '/dir2/dir3/b'])
        obj = cs['/dir1']
        self.assertEqual(obj.mode, 0o775)

    def test_inode_map(self):

        def check_it(target):
            d = {k: sorted(v) for k, v in cs.inode_map().items()}
            target = {k: sorted(v) for k, v in target.items()}
            self.assertEqual(d, target)

        cs = contents.contentsSet()
        f1 = self.mk_file("/f", dev=1, inode=1)
        cs.add(f1)
        check_it({(1,1):[f1]})

        f2 = self.mk_file("/x", dev=1, inode=2)
        cs.add(f2)
        check_it({(1,1):[f1], (1,2):[f2]})

        f3 = self.mk_file("/y", dev=2, inode=1)
        cs.add(f3)
        check_it({(1,1):[f1], (1,2):[f2], (2,1):[f3]})

        f4 = self.mk_file("/z", dev=1, inode=1)
        cs.add(f4)
        check_it({(1,1):[f1, f4], (1,2):[f2], (2,1):[f3]})


class Test_offset_rewriting(TestCase):

    change_offset = staticmethod(contents.change_offset_rewriter)
    offset_insert = staticmethod(contents.offset_rewriter)

    def test_offset_rewriter(self):
        f = ["/foon/%i" % x for x in range(10)]
        f.extend("/foon/%i/blah" % x for x in range(5))
        f = [fs.fsFile(x, strict=False) for x in f]
        self.assertEqual(sorted(x.location for x in f),
            sorted(x.location for x in self.offset_insert('/', f)))
        self.assertEqual(
            sorted(f'/usr{x.location}' for x in f),
            sorted(x.location for x in self.offset_insert('/usr', f)))

    def test_it(self):
        f = ["/foon/%i" % x for x in range(10)]
        f.extend("/foon/%i/blah" % x for x in range(5))
        f = [fs.fsFile(x, strict=False) for x in f]
        self.assertEqual(sorted(x.location for x in f),
            sorted(y.location for y in self.change_offset('/usr', '/',
                (x.change_attributes(location=f'/usr{x.location}')
                    for x in f)
            )))
        self.assertEqual(sorted(x.location for x in f),
            sorted(y.location for y in self.change_offset('/usr', '/',
                (x.change_attributes(location=f'/usr/{x.location}')
                    for x in f)
            )))
        self.assertEqual(sorted("/usr" + x.location for x in f),
            sorted(y.location for y in self.change_offset('/', '/usr',
                (x.change_attributes(location=f'/{x.location}')
                    for x in f)
            )))



