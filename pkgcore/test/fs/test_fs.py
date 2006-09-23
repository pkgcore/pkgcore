# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.fs import fs
from twisted.trial import unittest

class Test_fsFile(unittest.TestCase):

    def test_init(self):
        raise NotImplementedError(self)
        pass
    test_init.todo = "implement..."
    
    test_change_attributes = test_init
    test_setattr = test_init
    test_real_location = test_init
    test_hash = test_init
    test_eq = test_init

for x in ("Dir", "Link", "Dev", "Fifo"):
    class missing_test(Test_fsFile):
        pass
    locals()["Test_fs%s" % x] = missing_test
    del missing_test
