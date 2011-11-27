# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

import os
import sys
import shutil
import tempfile
import logging

from pkgcore.test import TestCase
from snakeoil import lists

from pkgcore.test import silence_logging
from pkgcore import plugin

class LowPlug(object):
    priority = 0

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
high_plug = HighPlug()

pkgcore_plugins = {
    'plugtest': [
        DisabledPlug,
        high_plug,
        'pkgcore.test.test_plugin.LowPlug',
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
        plugin._global_cache.clear()
        method()
        mtime = os.path.getmtime(os.path.join(self.packdir, plugin.CACHE_FILENAME))
        method()
        plugin._global_cache.clear()
        method()
        method()
        self.assertEqual(
            mtime,
            os.path.getmtime(os.path.join(self.packdir, plugin.CACHE_FILENAME)))
        # We cannot write this since it contains an unimportable plugin.
        self.assertFalse(
            os.path.exists(os.path.join(self.packdir2, plugin.CACHE_FILENAME)))

    def _test_plug(self):
        import mod_testplug
        self.assertIdentical(None, plugin.get_plugin('spork', mod_testplug))
        plugins = list(plugin.get_plugins('plugtest', mod_testplug))
        self.assertEqual(2, len(plugins), plugins)
        plugin.get_plugin('plugtest', mod_testplug)
        self.assertEqual(
            'HighPlug',
            plugin.get_plugin('plugtest', mod_testplug).__class__.__name__)
        lines = list(open(os.path.join(self.packdir, plugin.CACHE_FILENAME)))
        self.assertEqual(3, len(lines))
        self.assertEqual(plugin.CACHE_HEADER + "\n", lines[0])
        lines.pop(0)
        lines.sort()
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug2.py')))
        self.assertEqual('plug2:%s:\n' % (mtime,), lines[0])
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug.py')))
        self.assertEqual(
            'plug:%s:plugtest,7,1:plugtest,0,pkgcore.test.test_plugin.LowPlug:plugtest,0,0\n'
                % (mtime,),
            lines[1])

    def test_plug(self):
        self._runit(self._test_plug)

    def _test_no_unneeded_import(self):
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        sys.modules.pop('mod_testplug.plug')
        # This one is not loaded if we are testing with a good cache.
        sys.modules.pop('mod_testplug.plug2', None)
        list(plugin.get_plugins('plugtest', mod_testplug))
        # Extra messages since getting all of sys.modules printed is annoying.
        self.assertIn('mod_testplug.plug', sys.modules, 'plug not loaded')
        self.assertNotIn('mod_testplug.plug2', sys.modules, 'plug2 loaded')

    def test_no_unneeded_import(self):
        self._runit(self._test_no_unneeded_import)

    @silence_logging(logging.root)
    def test_cache_corruption(self):
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        filename = os.path.join(self.packdir, plugin.CACHE_FILENAME)
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
        plugin._global_cache.clear()
        self._test_plug()
        good_mtime = os.path.getmtime(
            os.path.join(self.packdir, plugin.CACHE_FILENAME))
        plugin._global_cache.clear()
        self._test_plug()
        self.assertEqual(good_mtime, os.path.getmtime(
                os.path.join(self.packdir, plugin.CACHE_FILENAME)))
        self.assertNotEqual(good_mtime, corrupt_mtime)

    def test_rewrite_on_remove(self):
        filename = os.path.join(self.packdir, 'extra.py')
        plug = open(filename, 'w')
        try:
            plug.write('pkgcore_plugins = {"plugtest": [object()]}\n')
        finally:
            plug.close()

        plugin._global_cache.clear()
        import mod_testplug
        self.assertEqual(
            3, len(list(plugin.get_plugins('plugtest', mod_testplug))))

        os.unlink(filename)

        plugin._global_cache.clear()
        self._test_plug()

    @silence_logging(logging.root)
    def test_priority_caching(self):
        plug3 = open(os.path.join(self.packdir, 'plug3.py'), 'w')
        try:
            plug3.write('''
class LowPlug(object):
    priority = 6

pkgcore_plugins = {
    'plugtest': [LowPlug()],
}
''')
        finally:
            plug3.close()
        plug4 = open(os.path.join(self.packdir, 'plug4.py'), 'w')
        try:
            plug4.write('''
# First file tried, only a disabled plugin.
class HighDisabledPlug(object):
    priority = 15
    disabled = True

pkgcore_plugins = {
    'plugtest': [HighDisabledPlug()],
}
''')
        finally:
            plug4.close()
        plug5 = open(os.path.join(self.packdir, 'plug5.py'), 'w')
        try:
            plug5.write('''
# Second file tried, with a skipped low priority plugin.
class HighDisabledPlug(object):
    priority = 12
    disabled = True

class LowPlug(object):
    priority = 6

pkgcore_plugins = {
    'plugtest': [HighDisabledPlug(), LowPlug()],
}
''')
        finally:
            plug5.close()
        plug6 = open(os.path.join(self.packdir, 'plug6.py'), 'w')
        try:
            plug6.write('''
# Not tried, bogus priority.
class BogusPlug(object):
    priority = 'spoon'

pkgcore_plugins = {
    'plugtest': [BogusPlug()],
}
''')
        finally:
            plug6.close()
        self._runit(self._test_priority_caching)

    def _test_priority_caching(self):
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        sys.modules.pop('mod_testplug.plug', None)
        sys.modules.pop('mod_testplug.plug2', None)
        sys.modules.pop('mod_testplug.plug3', None)
        sys.modules.pop('mod_testplug.plug4', None)
        sys.modules.pop('mod_testplug.plug5', None)
        sys.modules.pop('mod_testplug.plug6', None)
        best_plug = plugin.get_plugin('plugtest', mod_testplug)
        from mod_testplug import plug
        self.assertEqual(plug.high_plug, best_plug)
        # Extra messages since getting all of sys.modules printed is annoying.
        self.assertIn('mod_testplug.plug', sys.modules, 'plug not loaded')
        self.assertNotIn('mod_testplug.plug2', sys.modules, 'plug2 loaded')
        self.assertNotIn('mod_testplug.plug3', sys.modules, 'plug3 loaded')
        self.assertIn('mod_testplug.plug4', sys.modules, 'plug4 not loaded')
        self.assertIn('mod_testplug.plug5', sys.modules, 'plug4 not loaded')
        self.assertNotIn('mod_testplug.plug6', sys.modules, 'plug6 loaded')

    @silence_logging(logging.root)
    def test_header_change_invalidates_cache(self):
        # Write the cache
        plugin._global_cache.clear()
        import mod_testplug
        list(plugin.get_plugins('testplug', mod_testplug))

        # Modify the cache.
        filename = os.path.join(self.packdir, plugin.CACHE_FILENAME)
        cache = list(open(filename))
        cache[0] = 'not really a pkgcore plugin cache\n'
        open(filename, 'w').write(''.join(cache))

        # And test if it is properly rewritten.
        plugin._global_cache.clear()
        self._test_plug()
