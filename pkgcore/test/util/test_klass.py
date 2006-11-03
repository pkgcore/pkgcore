# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.util import klass


class Test_native_GetAttrProxy(TestCase):
    kls = staticmethod(klass.native_GetAttrProxy)
    
    def test_it(self):
        class foo1(object):
            def __init__(self, obj):
                self.obj = obj
            __getattr__ = self.kls('obj')

        class foo2(object):
            pass
        
        o2 = foo2()
        o = foo1(o2)
        self.assertRaises(AttributeError, getattr, o, "blah")
        self.assertEqual(o.obj, o2)
        o2.foon = "dar"
        self.assertEqual(o.foon, "dar")
        o.foon = "foo"
        self.assertEqual(o.foon, 'foo')


class Test_CPY_GetAttrProxy(Test_native_GetAttrProxy):

    kls = staticmethod(klass.GetAttrProxy)
    if klass.GetAttrProxy is klass.native_GetAttrProxy:
        skip = "cpython extension isn't available"

    def test_sane_recursion_bail(self):
        # people are stupid; if protection isn't in place, we wind up blowing
        # the c stack, which doesn't result in a friendly Exception being
        # thrown.
        # results in a segfault.. so if it's horked, this will bail the test
        # runner.

        class c(object):
            __getattr__ = self.kls("obj")
        
        o = c()
        o.obj = o
        # now it's cyclical.
        self.assertRaises(RuntimeError, getattr, o, "hooey")
