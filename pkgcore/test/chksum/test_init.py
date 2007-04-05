# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.test import TestCase
from pkgcore import chksum


class Test_funcs(TestCase):

    # ensure we aren't mangling chksum state for other tests.
    def tearDown(self):
        chksum.__inited__ = False
        chksum.chksum_types.clear()
        chksum.init = self._saved_init

    def setUp(self):
        chksum.__inited__ = False
        chksum.chksum_types.clear()
        self._saved_init = chksum.init
        self._inited_count = 0
        def f():
            self._inited_count += 1
            chksum.__inited__ = True
        chksum.init = f

    def test_get_handlers(self):
        expected = {"x":1, "y":2}
        chksum.chksum_types.update(expected)
        self.assertEqual(expected, chksum.get_handlers())
        self.assertEqual(self._inited_count, 1)
        self.assertEqual(expected, chksum.get_handlers(None))
        self.assertEqual({"x":1}, chksum.get_handlers(["x"]))
        self.assertEqual(expected, chksum.get_handlers(["x", "y"]))
        self.assertEqual(self._inited_count, 1)

    def test_get_handler(self):
        self.assertRaises(KeyError, chksum.get_handler, "x")
        self.assertEqual(self._inited_count, 1)
        chksum.chksum_types["x"] = 1
        self.assertRaises(KeyError, chksum.get_handler, "y")
        chksum.chksum_types["y"] = 2
        self.assertEqual(1, chksum.get_handler("x"))
        self.assertEqual(2, chksum.get_handler("y"))
        self.assertEqual(self._inited_count, 1)

