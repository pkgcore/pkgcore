import pytest

from pkgcore.cache import errors, flat_hash
from snakeoil.chksum import LazilyHashedPath

from . import test_base


class db(flat_hash.database):

    def __setitem__(self, cpv, data):
        data['_chf_'] = test_base._chf_obj
        return flat_hash.database.__setitem__(self, cpv, data)

    def __getitem__(self, cpv):
        d = dict(flat_hash.database.__getitem__(self, cpv).items())
        d.pop(f'_{self.chf_type}_', None)
        return d


generic_data = \
    ("sys-libs/libtrash-2.4",
        (('DEPEND', 'virtual/libc dev-lang/perl'),
        ('DESCRIPTION', 'provides a trash can by intercepting calls...'),
        ('EAPI', ''),
        ('HOMEPAGE', 'http://pages.stern.nyu.edu/~marriaga/software/libtrash/'),
        ('IUSE', ''),
        ('KEYWORDS', '~amd64 ~ppc ~x86'),
        ('LICENSE', 'GPL-2'),
        ('PDEPEND', ''),
        ('RDEPEND', 'virtual/libc dev-lang/perl'),
        ('RESTRICT', ''),
        ('SLOT', '0'),
        ('SRC_URI', 'http://pages.stern.nyu.edu/~marriaga/software/blah.tgz'),
        ('_eclasses_',
            {
                'toolchain-funcs': LazilyHashedPath('/var/gentoo/repos/gentoo/eclass', mtime=1155996352),
                'multilib': LazilyHashedPath('/var/gentoo/repos/gentoo/eclass', mtime=1156014349),
                'eutils': LazilyHashedPath('/var/gentoo/repos/gentoo/eclass', mtime=1155996352),
                'portability': LazilyHashedPath('/var/gentoo/repos/gentoo/eclass', mtime=1141850196)
            }
        ),
        ('_mtime_', 1000),
    ),
)

class TestFlatHash:

    @pytest.fixture
    def db(self, tmp_path, request):
        return db(str(tmp_path), auxdbkeys=self.cache_keys, readonly=request.param)

    cache_keys = ("DEPENDS", "RDEPEND", "EAPI", "HOMEPAGE", "KEYWORDS",
        "LICENSE", "PDEPEND", "RESTRICT", "SLOT", "SRC_URI",
        "_eclasses_", "_mtime_")

    # truncating the original metadata we grabbed for 80 char...
    test_data = (generic_data,)

    @pytest.mark.parametrize("db", (False, ), indirect=True)
    def test_readwrite(self, db):
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            db[key] = d
        db.commit()

    @pytest.mark.parametrize("db", (True, ), indirect=True)
    def test_readonly(self, db):
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            with pytest.raises(errors.ReadOnly):
                db[key] = d

    @pytest.mark.parametrize("db", (False, ), indirect=True)
    def test_setitem(self, db):
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            db[key] = d
