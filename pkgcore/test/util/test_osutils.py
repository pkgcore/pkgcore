# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

import os

from twisted.trial import unittest

from pkgcore.util.osutils import native_readdir

from pkgcore.test.fs.test_util import TempDirMixin


class NativeListDirTest(unittest.TestCase, TempDirMixin):

    module = native_readdir

    def setUp(self):
        TempDirMixin.setUp(self)
        self.subdir = os.path.join(self.dir, 'dir')
        os.mkdir(self.subdir)
        f = open(os.path.join(self.dir, 'file'), 'w')
        f.close()
        os.mkfifo(os.path.join(self.dir, 'fifo'))

    def test_listdir(self):
        self.assertEquals(['dir', 'fifo', 'file'],
                          sorted(self.module.listdir(self.dir)))
        self.assertEquals([], self.module.listdir(self.subdir))

    def test_listdir_dirs(self):
        self.assertEquals(['dir'], self.module.listdir_dirs(self.dir))
        self.assertEquals([], self.module.listdir_dirs(self.subdir))

    def test_listdir_files(self):
        self.assertEquals(['file'], self.module.listdir_files(self.dir))
        self.assertEquals([], self.module.listdir_dirs(self.subdir))

    def test_missing(self):
        for func in (
            self.module.listdir,
            self.module.listdir_dirs,
            self.module.listdir_files,
            ):
            self.assertRaises(OSError, func, os.path.join(self.dir, 'spork'))

try:
    from pkgcore.util.osutils import _readdir
except ImportError:
    pass
else:
    class CPyListDirTest(NativeListDirTest):
        module = _readdir
