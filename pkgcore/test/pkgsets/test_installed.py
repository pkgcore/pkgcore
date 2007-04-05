# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.test import TestCase
from pkgcore.repository.util import SimpleTree
from pkgcore.pkgsets import installed

class FakePkg(object):

    package_is_real = True

    def __init__(self, *key):
        self.key = key

    @property
    def slotted_atom(self):
        return "%s/%s" % self.key[:2]

    @property
    def versioned_atom(self):
        return '%s/%s-%s' % self.key


class TestInstalled(TestCase):

    def test_iter(self):
        fake_vdb = SimpleTree({"dev-util": {"diffball":["1.0"],
            "bsdiff":["1.2", "1.3"]}}, pkg_klass=FakePkg)
        ipkgset = installed.Installed([fake_vdb])
        self.assertEqual(sorted(["dev-util/diffball",
            "dev-util/bsdiff", "dev-util/bsdiff"]),
            sorted(ipkgset))
        vpkgset = installed.VersionedInstalled([fake_vdb])
        self.assertEqual(sorted(["dev-util/diffball-1.0",
            "dev-util/bsdiff-1.2", "dev-util/bsdiff-1.3"]),
            sorted(vpkgset))
