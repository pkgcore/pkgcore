# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase, quiet_logger, protect_logging
from pkgcore import plugin
from pkgcore.util import lists

import os
import sys
import shutil
import tempfile
import logging


class ModulesTest(TestCase):

    def setUp(self):
        # Set up some test modules for our use.
        self.dir = tempfile.mkdtemp()
        self.dir2 = tempfile.mkdtemp()
        self.packdir = os.path.join(self.dir, 'mod_testplug')
        self.packdir2 = os.path.join(self.dir2, 'mod_testplug')
        os.mkdir(self.packdir)
        os.mkdir(self.packdir2)
        init = open(os.path.join(self.packdir, '__init__.py'), 'w')
        init.write('''
from pkgcore.plugins import extend_path

extend_path(__path__, __name__)
''')
        init.close()
        filename = os.path.join(self.packdir, 'plug.py')
        plug = open(filename, 'w')
        plug.write('''
class DisabledPlug(object):
    disabled = True

class HighPlug(object):
    priority = 7

class LowPlug(object):
    priority = 0

low_plug = LowPlug()

pkgcore_plugins = {
    'plugtest': [
        DisabledPlug,
        HighPlug(),
        low_plug,
    ]
}
''')
        plug.close()
        # Move the mtime 2 seconds into the past so the .pyc file has
        # a different mtime.
        st = os.stat(filename)
        os.utime(filename, (st.st_atime, st.st_mtime - 2))
        plug2 = open(os.path.join(self.packdir, 'plug2.py'), 'w')
        plug2.write('# I do not have any pkgcore_plugins for you!\n')
        plug2.close()
        plug = open(os.path.join(self.packdir2, 'plug.py'), 'w')
        plug.write('''
# This file is later on sys.path than the plug.py in packdir, so it should
# not have any effect on the tests.

class HiddenPlug(object):
    priority = 8

pkgcore_plugins = {'plugtest': [HiddenPlug]}
''')
        # Append it to the path
        sys.path.insert(0, self.dir2)
        sys.path.insert(0, self.dir)

    def tearDown(self):
        # pop the test module dir from path
        sys.path.pop(0)
        sys.path.pop(0)
        # and kill it
        shutil.rmtree(self.dir)
        shutil.rmtree(self.dir2)
        # make sure we don't keep the sys.modules entries around
        sys.modules.pop('mod_testplug', None)
        sys.modules.pop('mod_testplug.plug', None)
        sys.modules.pop('mod_testplug.plug2', None)

    def test_extend_path(self):
        import mod_testplug
        expected = lists.stable_unique(
            os.path.join(p, 'mod_testplug')
            for p in sys.path if os.path.isdir(p))
        self.assertEqual(
            expected, mod_testplug.__path__,
            set(expected) ^ set(mod_testplug.__path__))

    def _runit(self, method):
        plugin._cache = {}
        method()
        mtime = os.path.getmtime(os.path.join(self.packdir, 'plugincache'))
        method()
        plugin._cache = {}
        method()
        method()
        self.assertEqual(
            mtime, os.path.getmtime(os.path.join(self.packdir, 'plugincache')))
        # We cannot write this since it contains an unimportable plugin.
        self.assertFalse(
            os.path.exists(os.path.join(self.packdir2, 'plugincache')))

    def _test_plug(self):
        import mod_testplug
        self.assertIdentical(None, plugin.get_plugin('spork', mod_testplug))
        plugins = list(plugin.get_plugins('plugtest', mod_testplug))
        self.assertEqual(2, len(plugins), plugins)
        self.assertEqual(
            'HighPlug',
            plugin.get_plugin('plugtest', mod_testplug).__class__.__name__)
        lines = list(open(os.path.join(self.packdir, 'plugincache')))
        self.assertEqual(2, len(lines))
        lines.sort()
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug2.py')))
        self.assertEqual('plug2:%s:\n' % (mtime,), lines[0])
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug.py')))
        self.assertEqual('plug:%s:plugtest\n' % (mtime,), lines[1])

    def test_plug(self):
        self._runit(self._test_plug)

    def _test_no_unneeded_import(self):
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        sys.modules.pop('mod_testplug.plug')
        # This one is not loaded if we are testing with a good cache.
        sys.modules.pop('mod_testplug.plug2', None)
        list(plugin.get_plugins('plugtest', mod_testplug))
        self.assertIn('mod_testplug.plug', sys.modules)
        self.assertNotIn('mod_testplug.plug2', sys.modules)

    def test_no_unneeded_import(self):
        self._runit(self._test_no_unneeded_import)

    def test_cache_corruption(self):
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        filename = os.path.join(self.packdir, 'plugincache')
        cachefile = open(filename, 'a')
        try:
            cachefile.write('corruption\n')
        finally:
            cachefile.close()
        # Shift the file into the past a little or the rewritten file
        # will occasionally have the same mtime as the corrupt one.
        st = os.stat(filename)
        corrupt_mtime = st.st_mtime - 2
        os.utime(filename, (st.st_atime, corrupt_mtime))
        plugin._cache = {}
        self._test_plug()
        good_mtime = os.path.getmtime(
            os.path.join(self.packdir, 'plugincache'))
        plugin._cache = {}
        self._test_plug()
        self.assertEqual(good_mtime, os.path.getmtime(
                os.path.join(self.packdir, 'plugincache')))
        self.assertNotEqual(good_mtime, corrupt_mtime)

    @protect_logging(logging.root)
    def test_broken_module(self):
        logging.root.handlers = [quiet_logger]
        filename = os.path.join(self.packdir, 'bug.py')
        plug = open(filename, 'w')
        try:
            plug.write('this is not actually python\n')
        finally:
            plug.close()

        plugin._cache = {}
        self._test_plug()

        filename = os.path.join(self.packdir, 'plugincache')
        st = os.stat(filename)
        mtime = st.st_mtime - 2
        os.utime(filename, (st.st_atime, mtime))

        plugin._cache = {}
        self._test_plug()

        # Should never write a usable cache.
        self.assertNotEqual(
            mtime, os.path.getmtime(os.path.join(self.packdir, 'plugincache')))

    def test_rewrite_on_remove(self):
        filename = os.path.join(self.packdir, 'extra.py')
        plug = open(filename, 'w')
        try:
            plug.write('pkgcore_plugins = {"plugtest": [object()]}\n')
        finally:
            plug.close()

        plugin._cache = {}
        import mod_testplug
        self.assertEqual(
            3, len(list(plugin.get_plugins('plugtest', mod_testplug))))

        os.unlink(filename)

        plugin._cache = {}
        self._test_plug()
