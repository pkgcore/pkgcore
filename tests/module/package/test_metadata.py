from snakeoil.test import TestCase

from pkgcore.package import base, metadata


def make_pkg_kls(attrs=(), callbacks={}):

    class simple_pkg(base.base):
        _get_attr = callbacks
        __slots__ = ("_args", "_kwds", "_data", "_fetch_called",) + tuple(attrs)

        def __init__(self, *args, **kwds):
            self._args = args
            self._data = kwds.pop("data", {})
            self._kwds = kwds
            self._fetch_called = False

        __setattr__ = object.__setattr__

    class metadata_pkg(metadata.DeriveMetadataKls(simple_pkg)):

        __slots__ = ()
        def _fetch_metadata(self):
            self._fetch_called = True
            return self._data

    return metadata_pkg


class TestMetadataPackage(TestCase):

    def test_init(self):
        class repo:
            _parent_repo = "foon"

        kls = make_pkg_kls()
        o = kls(repo, "monkeys", dar=1)
        self.assertEqual(o._parent, repo)
        self.assertEqual(o.repo, "foon")
        self.assertEqual(o._args, ("monkeys",))
        self.assertEqual(o._kwds, {"dar":1})
        self.assertEqual(o._fetch_called, False)

    def test_getdata(self):
        kls = make_pkg_kls()
        o = kls(None, data={'a': 'b'})
        self.assertEqual(o.data, {'a': 'b'})
