# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.package import base
from pkgcore.util.currying import pre_curry

class TestBasePkg(unittest.TestCase):
   
    def test_setattr(self):
        self.assertRaises(AttributeError, base.base().__setattr__, "asdf", 1)

    def test_delattr(self):
        self.assertRaises(AttributeError, base.base().__delattr__, "asdf")

    def test_properties(self):
        o = base.base()
        for f in ("versioned_atom", "unversioned_atom"):
            self.assertRaises(NotImplementedError, getattr, o, f)
            self.assertRaises(AttributeError, o.__setattr__, f, "a")
            self.assertRaises(AttributeError, o.__delattr__, f)

    def test_getattr(self):
        class c(base.base):
            _get_attr = dict((str(x), pre_curry(lambda a,s:a, x))
                for x in xrange(10))
            _get_attr["a"] = lambda s:"foo"
        
        o = c()
        for x in xrange(10):
            self.assertEqual(getattr(o, str(x)), x)
        self.assertEqual(o.a, "foo")
