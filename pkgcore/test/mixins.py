# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import os
import shutil
import tempfile

from pkgcore.test import TestCase

class TempDirMixin(TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # force it, since sticky bits spread.
        os.chmod(self.dir, 0700)

    def tearDown(self):
        # change permissions back or rmtree can't kill it
        for root, dirs, files in os.walk(self.dir):
            for directory in dirs:
                os.chmod(os.path.join(root, directory), 0777)
        shutil.rmtree(self.dir)
