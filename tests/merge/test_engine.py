import pytest

from pkgcore.fs import livefs
from pkgcore.fs.contents import contentsSet
from pkgcore.merge.engine import MergeEngine

from ..fs.fs_util import fsDir, fsFile, fsSymlink
from .util import fake_engine


class fake_pkg:

    def __init__(self, contents, label=None):
        self.label = label
        self.contents = contents

    def __str__(self):
        return f"fake_pkg: {self.label}"


class TestMergeEngineCsets:

    simple_cset = list(fsFile(x) for x in ("/foon", "/usr/dar", "/blah"))
    simple_cset.extend(fsDir(x) for x in ("/usr", "/usr/lib"))
    simple_cset.append(fsSymlink("/usr/lib/blah", "../../blah"))
    simple_cset.append(fsSymlink("/broken-symlink", "dar"))
    simple_cset = contentsSet(simple_cset, mutable=False)

    def assertCsetEqual(self, cset1, cset2):
        if not isinstance(cset1, contentsSet):
            cset1 = contentsSet(cset1)
        if not isinstance(cset2, contentsSet):
            cset2 = contentsSet(cset2)
        assert cset1 == cset2

    def assertCsetNotEqual(self, cset1, cset2):
        if not isinstance(cset1, contentsSet):
            cset1 = contentsSet(cset1)
        if not isinstance(cset2, contentsSet):
            cset2 = contentsSet(cset2)
        assert cset1 == cset2

    def run_cset(self, target, engine, *args):
        return getattr(MergeEngine, target)(engine, engine.csets, *args)

    def test_generate_offset_cset(self):
        engine = fake_engine(csets={"new_cset":self.simple_cset},
            offset='/')
        def run(engine, cset):
            return self.run_cset('generate_offset_cset', engine,
                lambda e, c:c[cset])

        self.assertCsetEqual(self.simple_cset, run(engine, 'new_cset'))
        engine.offset = '/foon/'
        run(engine, 'new_cset')
        self.assertCsetEqual(self.simple_cset.insert_offset(engine.offset),
            run(engine, 'new_cset'))

    def test_get_pkg_contents(self):
        new_cset = MergeEngine.get_pkg_contents(None, None, fake_pkg(self.simple_cset))
        self.assertCsetEqual(self.simple_cset, new_cset)
        # must differ; shouldn't be modifying the original cset
        assert self.simple_cset is not new_cset

    def test_get_remove_cset(self):
        files = contentsSet(self.simple_cset.iterfiles(invert=True))
        engine = fake_engine(csets={'install':files,
            'old_cset':self.simple_cset})
        self.assertCsetEqual(self.simple_cset.iterfiles(),
            self.run_cset('get_remove_cset', engine))

    def test_get_replace_cset(self):
        files = contentsSet(self.simple_cset.iterfiles(invert=True))
        engine = fake_engine(csets={'install':files,
            'old_cset':self.simple_cset})
        self.assertCsetEqual(files,
            self.run_cset('get_replace_cset', engine))

    def test_rewrite_awareness(self, tmp_path):
        src = contentsSet(self.simple_cset)
        src.add(fsFile("/usr/lib/donkey"))
        trg = src.difference(["/usr/lib/donkey"])
        trg.add(fsFile("/usr/lib64/donkey"))
        trg = trg.insert_offset(str(tmp_path))
        (tmp_path / 'usr' / 'lib64').mkdir(parents=True)
        (tmp_path / 'usr' / 'lib').symlink_to("lib64")
        pkg = fake_pkg(src)
        engine = MergeEngine.install(str(tmp_path), pkg, offset=str(tmp_path))
        result = engine.csets['resolved_install']
        assert set(result.iterfiles()) == set(trg.iterfiles())

    @pytest.mark.skip("contentset should handle this")
    def test_symlink_awareness(self, tmp_path):
        src = contentsSet(self.simple_cset)
        src.add(fsFile("/usr/lib/blah/donkey"))
        trg = src.difference(["/usr/lib/blah/donkey"])
        trg.add(fsFile("/blah/donkey"))
        trg = trg.insert_offset(str(tmp_path))
        pkg = fake_pkg(src)
        engine = MergeEngine.install(str(tmp_path), pkg, offset=str(tmp_path))
        result = engine.csets['new_cset']
        assert set(result.iterfiles()) == set(trg.iterfiles())

    def test_get_livefs_intersect_cset(self, tmp_path):
        old_cset = self.simple_cset.insert_offset(str(tmp_path))
        # have to add it; scan adds the root node
        old_cset.add(fsDir(str(tmp_path)))
        (tmp_path / 'usr').mkdir()
        (tmp_path / 'usr' / 'dar').touch()
        (tmp_path / 'foon').touch()
        # note that this *is* a sym in the cset; adding this specific
        # check so that if the code differs, the test breaks, and the tests
        # get updated (additionally, folks may not be aware of the potential)
        (tmp_path / 'broken-symlink').touch()
        engine = fake_engine(csets={'test':old_cset})
        existent = livefs.scan(str(tmp_path))
        generated = self.run_cset('_get_livefs_intersect_cset', engine,
            'test')
        assert generated == existent
