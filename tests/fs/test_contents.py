import os
from functools import partial

import pytest
from pkgcore.fs import contents, fs

mk_file = partial(fs.fsFile, strict=False)
mk_dir  = partial(fs.fsDir, strict=False)
mk_link = partial(fs.fsLink, strict=False)
mk_dev  = partial(fs.fsDev, strict=False)
mk_fifo = partial(fs.fsFifo, strict=False)


class TestContentsSet:
    files = list(map(mk_file, ["/etc/blah", "/etc/foo", "/etc/dar",
        "/tmp/dar",
        "/tmp/blah/foo/long/ass/file/name/but/not/that/bad/really"]))
    dirs = list(map(mk_dir, ["/tmp", "/blah", "/tmp/dar",
        "/usr/", "/usr/bin"]))
    links = [fs.fsLink(x, os.path.dirname(x), strict=False) for x in
        ["/tmp/foo", "/usr/X11R6/lib", "/nagga/noo"]]
    devs = list(map(mk_dev,
        [f"dev/{x}" for x in ["sda1", "hda", "hda2", "disks/ide1"]]))
    fifos = list(map(mk_fifo,
        [f"tmp/{y}" for y in ("dar", "boo", "bah")]))
    all = dirs + links + devs + fifos

    def test_init(self):
        with pytest.raises(TypeError):
            contents.contentsSet(self.all + [1])
        contents.contentsSet(self.all)
        contents.contentsSet(self.all, mutable=True)
        # test to ensure no one screwed up the optional initials
        # making it mandatory
        assert len(contents.contentsSet()) == 0

    def test_add(self):
        cs = contents.contentsSet(self.files + self.dirs, mutable=True)
        for x in self.links:
            cs.add(x)
            assert x in cs
        assert len(cs) == len(set(x.location for x in self.files + self.dirs + self.links))
        with pytest.raises(AttributeError):
            contents.contentsSet(mutable=False).add(self.devs[0])
        with pytest.raises(TypeError):
            cs.add(1)
        with pytest.raises(TypeError):
            cs.add(self.fifos)

    def test_remove(self):
        with pytest.raises(AttributeError):
            contents.contentsSet(mutable=False).remove(self.devs[0])
        with pytest.raises(AttributeError):
            contents.contentsSet(mutable=False).remove(1)
        cs = contents.contentsSet(self.all, mutable=True)
        for x in self.all:
            cs.remove(x)
        cs = contents.contentsSet(self.all, mutable=True)
        for location in (x.location for x in self.all):
            cs.remove(location)
        assert len(cs) == 0
        with pytest.raises(KeyError):
            cs.remove(self.all[0])

    def test_contains(self):
        cs = contents.contentsSet(mutable=True)
        for x in [y[0] for y in [
                self.files, self.dirs, self.links, self.devs, self.fifos]]:
            assert x not in cs
            assert x.location not in cs
            cs.add(x)
            assert x in cs
            assert x.location in cs
            cs.remove(x)

    def test_clear(self):
        cs = contents.contentsSet(self.all, mutable=True)
        assert len(cs) > 0
        cs.clear()
        assert len(cs) == 0

    def test_len(self):
        assert len(contents.contentsSet(self.all)) == len(self.all)

    fs_types = (
        pytest.param("files", fs.fsFile, id="files"),
        pytest.param("dirs", fs.fsDir, id="dirs"),
        pytest.param("links", fs.fsLink, id="links"),
        pytest.param("devs", fs.fsDev, id="devs"),
        pytest.param("fifos", fs.fsFifo, id="fifos"),
    )

    @pytest.mark.parametrize(("name", "obj_class"), fs_types)
    def test_iterobj(self, name, obj_class):
        s = set(getattr(self, name))
        cs = contents.contentsSet(s)
        forced_name = "iter" + name

        s2 = set(getattr(cs, forced_name)())
        if obj_class is not None:
            for x in s2:
                # post_curry(self.assertTrue, obj_class)(x)
                assert bool(x)
        assert s == s2

        # inversion tests now.
        s3 = set(getattr(cs, forced_name)(invert=True))
        for x in s3:
            # post_curry(self.assertFalse, obj_class)(x)
            assert not bool(x)

        assert s.symmetric_difference(s2) == s3

    @pytest.mark.parametrize(("name", "obj_class"), fs_types)
    def test_listobj(self, name, obj_class):
        valid_list = getattr(self, name)
        cs = contents.contentsSet(valid_list)
        test_list = getattr(cs, name)()
        if obj_class is not None:
            for x in test_list:
                assert isinstance(x, obj_class)
        assert set(test_list) == set(valid_list)

    def test_iterobj_all(self):
        s = set(self.all)
        assert set(contents.contentsSet(s)) == s

    def test_check_instance(self):
        for x in [y[0] for y in [
                self.files, self.dirs, self.links, self.devs, self.fifos]]:
            assert tuple(contents.check_instance(x)) == (x.location, x)
        with pytest.raises(TypeError):
            contents.check_instance(1)


    def check_set_op(self, name, ret, source=None):
        if source is None:
            source = ([fs.fsDir("/tmp", strict=False)],
                      [fs.fsFile("/tmp", strict=False)])

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(c2)
            c3 = c1
        else:
            c3 = getattr(c1, name)(c2)
        assert set(ret) == {x.location for x in c3}

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(iter(c2))
            c3 = c1
        else:
            c3 = getattr(c1, name)(iter(c2))
        assert set(ret) == {x.location for x in c3}

    fstrings = {"/a", "/b", "/c", "/d"}
    f = tuple(map(mk_file, fstrings))

    @pytest.mark.parametrize("name, ret, source", (
        pytest.param("intersection", {"/tmp"}, None, id="intersection"),
        pytest.param("intersection_update", {"/tmp"}, None, id="intersection_update"),
        pytest.param("difference", set(), None, id="difference"),
        pytest.param("difference_update", set(), None, id="difference_update"),
        pytest.param("symmetric_difference", set(), None, id="symmetric_difference"),
        pytest.param("symmetric_difference_update", set(), None, id="symmetric_difference_update"),

        pytest.param("union", {"/tmp"}, None, id="union1"),
        pytest.param("union", fstrings, (f[:2], f[2:]), id="union2"),
        pytest.param("symmetric_difference", fstrings, (f[:2], f[2:]), id="symmetric_difference2"),
        pytest.param("symmetric_difference_update", fstrings, (f[:2], f[2:]), id="symmetric_difference_update2"),
    ))
    def test_check_set_op(self, name, ret, source):
        if source is None:
            source = ([fs.fsDir("/tmp", strict=False)],
                      [fs.fsFile("/tmp", strict=False)])

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(c2)
            c3 = c1
        else:
            c3 = getattr(c1, name)(c2)
        assert {x.location for x in c3} == ret

        c1, c2 = [contents.contentsSet(x) for x in source]
        if name.endswith("_update"):
            getattr(c1, name)(iter(c2))
            c3 = c1
        else:
            c3 = getattr(c1, name)(iter(c2))
        assert {x.location for x in c3} == ret

    del f, fstrings

    def check_complex_set_op(self, name, required, data1, data2):
        cset1 = contents.contentsSet(data1)
        cset2 = contents.contentsSet(data2)
        f = getattr(cset1, name)
        got = f(cset2)
        assert got == required, \
            f"{name}: expected {required}, got {got}\ncset1={cset1!r}\ncset2={cset2!r}"

    @pytest.mark.parametrize(("required", "data1", "data2"), (
        (True, [mk_file("/foon")], [mk_file("/foon")]),
        (False, [mk_file("/foon")], [mk_file("/dev")]),
        (False, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
        (True, [mk_file("/dev"), mk_file("/dar")],
            [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")]),
    ))
    def test_issubset(self, required, data1, data2):
        self.check_complex_set_op("issubset", required, data1, data2)

    @pytest.mark.parametrize(("required", "data1", "data2"), (
        (True, [mk_file("/foon")], [mk_file("/foon")]),
        (False, [mk_file("/foon")], [mk_file("/dev")]),
        (True, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
        (False, [mk_file("/dev")], [mk_file("/dev"), mk_file("/dev2")]),
    ))
    def test_issuperset(self, required, data1, data2):
        self.check_complex_set_op("issuperset", required, data1, data2)

    @pytest.mark.parametrize(("required", "data1", "data2"), (
        (False, [mk_file("/foon")], [mk_file("/foon")]),
        (True, [mk_file("/foon")], [mk_file("/dev")]),
        (False, [mk_file("/dev"), mk_file("/dar")], [mk_file("/dev")]),
        (False, [mk_file("/dev"), mk_file("/dar")],
            [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")]),
        (False, [mk_file("/dev"), mk_file("/dar")],
            [mk_file("/dev"), mk_file("/dar"), mk_file("/asdf")]),
        (True, [mk_file("/dev"), mk_file("/dar")],
            [mk_file("/dev2"), mk_file("/dar2"), mk_file("/asdf")]),
    ))
    def test_isdisjoint(self, required, data1, data2):
        self.check_complex_set_op("isdisjoint", required, data1, data2)

    def test_child_nodes(self):
        assert {'/usr', '/usr/bin', '/usr/foo'} == {
            x.location for x in contents.contentsSet(
                [mk_dir("/usr"), mk_dir("/usr/bin"), mk_file("/usr/foo")])}

    def test_map_directory_structure(self):
        old = contents.contentsSet([mk_dir("/dir"),
            mk_link("/sym", "dir")])
        new = contents.contentsSet([mk_file("/sym/a"),
            mk_dir("/sym")])
        # verify the machinery is working as expected.
        ret = new.map_directory_structure(old)
        assert set(ret) == {mk_dir("/dir"), mk_file("/dir/a")}

        # test recursion next.
        old.add(mk_link("/dir/sym", "dir2"))
        old.add(mk_dir("/dir/dir2"))
        new.add(mk_file("/dir/sym/b"))
        new.add(mk_dir("/sym/sym"))

        ret = new.map_directory_structure(old)
        assert set(ret) == {mk_dir("/dir"), mk_file("/dir/a"),
            mk_dir("/dir/dir2"), mk_file("/dir/dir2/b")}


    def test_add_missing_directories(self):
        src = [mk_file("/dir1/a"), mk_file("/dir2/dir3/b"),
            mk_dir("/dir1/dir4")]
        cs = contents.contentsSet(src)
        cs.add_missing_directories()
        assert {x.location for x in cs} == \
            {'/dir1', '/dir1/a', '/dir1/dir4', '/dir2', '/dir2/dir3', '/dir2/dir3/b'}
        obj = cs['/dir1']
        assert obj.mode == 0o775

    def test_inode_map(self):

        def check_it(target):
            d = {k: set(v) for k, v in cs.inode_map().items()}
            target = {k: set(v) for k, v in target.items()}
            assert d == target

        cs = contents.contentsSet()
        f1 = mk_file("/f", dev=1, inode=1)
        cs.add(f1)
        check_it({(1,1):[f1]})

        f2 = mk_file("/x", dev=1, inode=2)
        cs.add(f2)
        check_it({(1,1):[f1], (1,2):[f2]})

        f3 = mk_file("/y", dev=2, inode=1)
        cs.add(f3)
        check_it({(1,1):[f1], (1,2):[f2], (2,1):[f3]})

        f4 = mk_file("/z", dev=1, inode=1)
        cs.add(f4)
        check_it({(1,1):[f1, f4], (1,2):[f2], (2,1):[f3]})


class Test_offset_rewriting:

    change_offset = staticmethod(contents.change_offset_rewriter)
    offset_insert = staticmethod(contents.offset_rewriter)

    def test_offset_rewriter(self):
        f = [f"/foon/{x}" for x in range(10)]
        f.extend(f"/foon/{x}/blah" for x in range(5))
        f = [fs.fsFile(x, strict=False) for x in f]
        assert {x.location for x in f} == {x.location for x in self.offset_insert('/', f)}
        assert {f'/usr{x.location}' for x in f} == {x.location for x in self.offset_insert('/usr', f)}

    def test_change_offset(self):
        f = [f"/foon/{x}" for x in range(10)]
        f.extend(f"/foon/{x}/blah" for x in range(5))
        f = [fs.fsFile(x, strict=False) for x in f]
        assert {x.location for x in f} == {
            y.location
            for y in self.change_offset('/usr', '/', (
                x.change_attributes(location=f'/usr{x.location}') for x in f))}
        assert {x.location for x in f} == {
            y.location
            for y in self.change_offset('/usr', '/', (
                x.change_attributes(location=f'/usr/{x.location}') for x in f))}
        assert {f'/usr{x.location}' for x in f} == {
            y.location
            for y in self.change_offset('/', '/usr', (
                x.change_attributes(location=f'/{x.location}') for x in f))}
