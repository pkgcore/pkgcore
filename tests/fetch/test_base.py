import os
from functools import partial

import pytest
from snakeoil import data_source
from snakeoil.chksum import get_handlers

from pkgcore.fetch import base, errors, fetchable

repeating_str = 'asdf'
data = repeating_str * 4000
handlers = get_handlers()


from snakeoil.mappings import LazyValDict


def _callback(chf):
    return handlers[chf](data_source.data_source(data))
chksums = LazyValDict(frozenset(handlers.keys()), _callback)

# get a non size based chksum
known_chksum = [x for x in handlers.keys() if x != "size"][0]

class TestFetcher:

    @pytest.fixture(autouse=True)
    def _setup(self, tmpdir):
        self.fp = os.path.join(str(tmpdir), "test")
        self.obj = fetchable(self.fp, chksums=chksums)
        self.fetcher = base.fetcher()

    def write_data(self, data=data):
        with open(self.fp, "w") as f:
            f.write(data)

    def test__call__(self):
        l = []
        class c(base.fetcher):
            def fetch(self, *a, **kw):
                l.extend((a, kw))

        o = c()
        o.fetch(1, foon=True)
        assert [(1,), {"foon": True}] == l
        self.write_data()
        assert self.fetcher._verify(self.fp, self.obj) == None
        self.write_data("asdf")
        with pytest.raises(errors.FetchError) as excinfo:
            self.fetcher._verify(self.fp, self.obj)
        assert excinfo.value.resumable

    def test_verify_all_chksums(self):
        self.write_data()
        subhandlers = dict([list(handlers.items())[0]])
        with pytest.raises(errors.RequiredChksumDataMissing):
            self.fetcher._verify(self.fp, self.obj, handlers=subhandlers)
        self.fetcher._verify(self.fp, self.obj)
        assert None == self.fetcher._verify(
            self.fp, self.obj, handlers=subhandlers, all_chksums=False)

    def test_size_verification_first(self):
        self.write_data()
        chksum_data = dict(chksums.items())
        l = []
        def f(chf, fp):
            l.append(chf)
            return chksum_data[chf]
        subhandlers = {"size": partial(f, 'size'), known_chksum:partial(f, known_chksum)}

        # exact size verification
        self.fetcher._verify(self.fp, self.obj, handlers=subhandlers, all_chksums=False)
        assert ['size', known_chksum] == l
        for x in (-100, 100):
            while l:
                l.pop(-1)
            chksum_data["size"] = chksums["size"] + x
            if x > 0:
                with pytest.raises(errors.ChksumFailure) as excinfo:
                    self.fetcher._verify(
                        self.fp, self.obj, handlers=subhandlers, all_chksums=False)
                assert excinfo.value.chksum == 'size'
            else:
                with pytest.raises(errors.FetchError) as excinfo:
                    self.fetcher._verify(
                        self.fp, self.obj, handlers=subhandlers, all_chksums=False)
                assert excinfo.value.resumable
            assert ['size'] == l

    def test_normal(self):
        self.write_data()
        assert self.fetcher._verify(self.fp, self.obj) == None
        self.write_data(data[:-1])
        with pytest.raises(errors.FetchError) as excinfo:
            self.fetcher._verify(self.fp, self.obj)
        assert excinfo.value.resumable
        # verify it returns -2 for missing file paths.
        os.unlink(self.fp)
        with pytest.raises(errors.MissingDistfile) as excinfo:
            self.fetcher._verify(self.fp, self.obj)
        assert excinfo.value.resumable
        self.write_data(data + "foon")
        with pytest.raises(errors.ChksumFailure) as excinfo:
            self.fetcher._verify(self.fp, self.obj)
        assert excinfo.value.chksum == 'size'

        # verify they're ran one, and only once
        l = []
        def f(chf, fp):
            l.append(chf)
            return chksums[chf]

        alt_handlers = {chf: partial(f, chf) for chf in chksums}
        assert None == self.fetcher._verify(self.fp, self.obj, handlers=alt_handlers)
        assert sorted(l) == sorted(alt_handlers)
