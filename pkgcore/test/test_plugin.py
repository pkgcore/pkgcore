# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase
from pkgcore import plugin

import os
import sys
import shutil
import tempfile


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

    def _runit(self, method):
        plugin._cache = {}
        method()
        mtime = os.path.getmtime(os.path.join(self.packdir, 'plugincache'))
        method()
        plugin._cache = {}
        method()
        method()
        self.assertEquals(
            mtime, os.path.getmtime(os.path.join(self.packdir, 'plugincache')))
        # We cannot write this since it contains an unimportable plugin.
        self.assertFalse(
            os.path.exists(os.path.join(self.packdir2, 'plugincache')))

    def _test_plug(self):
        import mod_testplug
        self.assertIdentical(None, plugin.get_plugin('spork', mod_testplug))
        plugins = list(plugin.get_plugins('plugtest', mod_testplug))
        self.assertEquals(2, len(plugins), plugins)
        self.assertEquals(
            'HighPlug',
            plugin.get_plugin('plugtest', mod_testplug).__class__.__name__)
        lines = list(open(os.path.join(self.packdir, 'plugincache')))
        self.assertEquals(2, len(lines))
        lines.sort()
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug2.py')))
        self.assertEquals('plug2:%s:\n' % (mtime,), lines[0])
        mtime = int(os.path.getmtime(os.path.join(self.packdir, 'plug.py')))
        self.assertEquals('plug:%s:plugtest\n' % (mtime,), lines[1])

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
