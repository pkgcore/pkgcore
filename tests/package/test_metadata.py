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


class TestMetadataPackage:

    def test_init(self):
        class repo:
            _parent_repo = "foon"

        kls = make_pkg_kls()
        o = kls(repo, "monkeys", dar=1)
        assert o._parent == repo
        assert o.repo == "foon"
        assert o._args == ("monkeys",)
        assert o._kwds == {"dar": 1}
        assert not o._fetch_called

    def test_getdata(self):
        kls = make_pkg_kls()
        o = kls(None, data={'a': 'b'})
        assert o.data == {'a': 'b'}
