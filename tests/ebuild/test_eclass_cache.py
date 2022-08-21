import os

import pytest

from pkgcore.ebuild import eclass_cache
from snakeoil import data_source
from snakeoil.chksum import LazilyHashedPath
from snakeoil.osutils import pjoin


class FakeEclassCache(eclass_cache.base):

    def __init__(self, path):
        eclass_cache.base.__init__(self, location=path, eclassdir=path)
        self.eclasses = {
            "eclass1":LazilyHashedPath(path, mtime=100),
            "eclass2":LazilyHashedPath(path, mtime=200)}


class TestBase:

    @pytest.fixture(autouse=True)
    def _setup(self):
        path = '/nonexistent/path/'
        self.ec = FakeEclassCache(path)
        self.ec_locs = {"eclass1": path, "eclass2": path}

    @pytest.mark.parametrize(('result', 'ec', 'mtime'), (
        (False, 'eclass3', 100),
        (True,  'eclass1', 100),
        (False, 'eclass1', 200),
    ))
    def test_rebuild_eclass_entry(self, result, ec, mtime):
        data = [(ec, [('mtime', mtime)])]
        got = self.ec.rebuild_cache_entry(data)
        assert bool(got) == result

    def test_get_eclass_data(self):
        keys = list(self.ec.eclasses.keys())
        data = self.ec.get_eclass_data([])
        assert data is self.ec.get_eclass_data([])
        data = self.ec.get_eclass_data(keys)
        assert data is self.ec.get_eclass_data(keys)
        assert set(keys) == set(data)
        data = self.ec.get_eclass_data(["eclass1"])
        assert data == {'eclass1': self.ec.eclasses['eclass1']}


class TestEclassCache(TestBase):

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        for x, mtime in (("eclass1", 100), ("eclass2", 200)):
            (path := tmp_path / f"{x}.eclass").touch()
            os.utime(path, (mtime, mtime))
        # insert a crap file to ensure it doesn't grab it.
        (path := tmp_path / "foon-eclass").touch()
        self.ec = eclass_cache.cache(str(tmp_path))
        self.ec_locs = {"eclass1": str(tmp_path), "eclass2": str(tmp_path)}

    def test_get_eclass(self):
        for x in ("eclass1", "eclass2"):
            handle = self.ec.get_eclass(x)
            assert isinstance(handle, data_source.local_source)
            assert pjoin(self.ec_locs[x], f"{x}.eclass") == handle.path

        # note an eclass, thus shouldn't grab it.
        assert self.ec.get_eclass("foon") is None
        assert self.ec.get_eclass("foon-eclass") is None


class TestStackedCaches(TestEclassCache):

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        (loc1 := tmp_path / "stack1").mkdir()
        (loc1 / 'eclass1.eclass').touch()
        os.utime(loc1 / 'eclass1.eclass', (100, 100))
        ec1 = eclass_cache.cache(str(loc1))

        (loc2 := tmp_path / "stack2").mkdir()
        (loc2 / 'eclass2.eclass').touch()
        os.utime(loc2 / 'eclass2.eclass', (100, 100))
        ec2 = eclass_cache.cache(str(loc2))
        self.ec = eclass_cache.StackedCaches([ec1, ec2])
        self.ec_locs = {"eclass1": str(loc1), "eclass2": str(loc2)}
        # make a shadowed file to verify it's not seen
        (loc2 / 'eclass1.eclass').touch()
