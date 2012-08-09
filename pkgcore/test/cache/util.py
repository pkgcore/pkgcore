# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.test import TestCase
from pkgcore.cache import errors
from snakeoil.chksum import LazilyHashedPath

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
        ('PROVIDE', ''),
        ('RDEPEND', 'virtual/libc dev-lang/perl'),
        ('RESTRICT', ''),
        ('SLOT', '0'),
        ('SRC_URI', 'http://pages.stern.nyu.edu/~marriaga/software/blah.tgz'),
        ('_eclasses_',
            {
                'toolchain-funcs': LazilyHashedPath('/usr/portage/eclass', mtime=1155996352L),
                'multilib': LazilyHashedPath('/usr/portage/eclass', mtime=1156014349L),
                'eutils': LazilyHashedPath('/usr/portage/eclass', mtime=1155996352L),
                'portability': LazilyHashedPath('/usr/portage/eclass', mtime=1141850196L)
            }
        ),
        ('_mtime_', 1000),
    ),
)

class GenericCacheMixin(TestCase):

    cache_keys = ("DEPENDS", "RDEPEND", "EAPI", "HOMEPAGE", "KEYWORDS",
        "LICENSE", "PDEPEND", "PROVIDE", "RESTRICT", "SLOT", "SRC_URI",
        "_eclasses_", "_mtime_")

    # truncating the original metadata we grabbed for 80 char...
    test_data = (generic_data,)

    def get_db(self, readonly=False):
        raise NotImplementedError(
            self, "get_db- must be overriden for test mixin, "
            "setting self.db to a cache instance ")

    def test_readonly(self):
        db = self.get_db(False)
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            db[key] = d
        db.commit()
        db = self.get_db(True)
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            self.assertRaises(errors.ReadOnly, db.__setitem__, key, d)

    def test_setitem(self):
        db = self.get_db(False)
        for key, raw_data in self.test_data:
            d = dict(raw_data)
            db[key] = d

