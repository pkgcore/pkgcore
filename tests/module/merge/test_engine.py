import os

from snakeoil.osutils import pjoin
from snakeoil.test import TestCase
from snakeoil.test.mixins import tempdir_decorator

from pkgcore.fs import livefs
from pkgcore.fs.contents import contentsSet
from pkgcore.merge import engine

from ..fs.fs_util import fsDir, fsFile, fsSymlink
from .util import fake_engine


class fake_pkg:

    def __init__(self, contents, label=None):
        self.label = label
        self.contents = contents

    def __str__(self):
        return f"fake_pkg: {self.label}"


class Test_MergeEngineCsets(TestCase):

    simple_cset = list(fsFile(x) for x in ("/foon", "/usr/dar", "/blah"))
    simple_cset.extend(fsDir(x) for x in ("/usr", "/usr/lib"))
    simple_cset.append(fsSymlink("/usr/lib/blah", "../../blah"))
    simple_cset.append(fsSymlink("/broken-symlink", "dar"))
    simple_cset = contentsSet(simple_cset, mutable=False)

    kls = engine.MergeEngine

    def assertCsetEqual(self, cset1, cset2):
        if not isinstance(cset1, contentsSet):
            cset1 = contentsSet(cset1)
        if not isinstance(cset2, contentsSet):
            cset2 = contentsSet(cset2)
        self.assertEqual(cset1, cset2, reflective=False)

    def assertCsetNotEqual(self, cset1, cset2):
        if not isinstance(cset1, contentsSet):
            cset1 = contentsSet(cset1)
        if not isinstance(cset2, contentsSet):
            cset2 = contentsSet(cset2)
        self.assertNotEqual(cset1, cset2, reflective=False)

    def run_cset(self, target, engine, *args):
        return getattr(self.kls, target)(engine, engine.csets, *args)

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
        new_cset = self.kls.get_pkg_contents(None, None, fake_pkg(self.simple_cset))
        self.assertCsetEqual(self.simple_cset, new_cset)
        # must differ; shouldn't be modifying the original cset
        self.assertNotIdentical(self.simple_cset, new_cset)

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

    @tempdir_decorator
    def test_rewrite_awareness(self):
        src = contentsSet(self.simple_cset)
        src.add(fsFile("/usr/lib/donkey"))
        trg = src.difference(["/usr/lib/donkey"])
        trg.add(fsFile("/usr/lib64/donkey"))
        trg = trg.insert_offset(self.dir)
        os.mkdir(pjoin(self.dir, 'usr'))
        os.mkdir(pjoin(self.dir, 'usr', 'lib64'))
        os.symlink('lib64', pjoin(self.dir, 'usr', 'lib'))
        pkg = fake_pkg(src)
        engine = self.kls.install(self.dir, pkg, offset=self.dir)
        result = engine.csets['resolved_install']
        self.assertEqual(sorted(result.iterfiles()), sorted(trg.iterfiles()))

    @tempdir_decorator
    def test_symlink_awareness(self):
        src = contentsSet(self.simple_cset)
        src.add(fsFile("/usr/lib/blah/donkey"))
        trg = src.difference(["/usr/lib/blah/donkey"])
        trg.add(fsFile("/blah/donkey"))
        trg = trg.insert_offset(self.dir)
        pkg = fake_pkg(src)
        engine = self.kls.install(self.dir, pkg, offset=self.dir)
        result = engine.csets['new_cset']
        self.assertEqual(sorted(result.iterfiles()), sorted(trg.iterfiles()))
    test_symlink_awareness.skip = "contentset should handle this"

    @tempdir_decorator
    def test__get_livefs_intersect_cset(self):
        old_cset = self.simple_cset.insert_offset(self.dir)
        # have to add it; scan adds the root node
        old_cset.add(fsDir(self.dir))
        os.mkdir(pjoin(self.dir, "usr"))
        open(pjoin(self.dir, "usr", "dar"), 'w').close()
        open(pjoin(self.dir, 'foon'), 'w').close()
        # note that this *is* a sym in the cset; adding this specific
        # check so that if the code differs, the test breaks, and the tests
        # get updated (additionally, folks may not be aware of the potential)
        open(pjoin(self.dir, 'broken-symlink'), 'w').close()
        engine = fake_engine(csets={'test':old_cset})
        existent = livefs.scan(self.dir)
        generated = self.run_cset('_get_livefs_intersect_cset', engine,
            'test')
        self.assertEqual(generated, existent)
