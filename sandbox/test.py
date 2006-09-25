#!/usr/bin/env python

# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Very minimal test runner."""

import os
import sys
import unittest
from pkgcore import test
from pkgcore.util import modules

if __name__ == '__main__':
    suites = []
    testpath = test.__path__[0]
    for root, dirs, files in os.walk(testpath):
        if '__init__.py' not in files:
            continue
        prefix = root[len(testpath):].replace(os.sep, '.')
        for mod in files:
            if mod.startswith('test') and mod.endswith('.py'):
                module = modules.load_module('pkgcore.test%s.%s' % (
                        prefix, mod[:-3]))
                suite = unittest.defaultTestLoader.loadTestsFromModule(module)
                suites.append(suite)
    result = unittest.TextTestRunner().run(unittest.TestSuite(suites))
    sys.exit(not result.wasSuccessful())
