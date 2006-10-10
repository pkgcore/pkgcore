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
        # set up some test modules for our use
        self.dir = tempfile.mkdtemp()
        self.packdir = os.path.join(self.dir, 'mod_testplug')
        os.mkdir(self.packdir)
        # create an empty file
        open(os.path.join(self.packdir, '__init__.py'), 'w').close()
        plug = open(os.path.join(self.packdir, 'plug.py'), 'w')
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
        plug2 = open(os.path.join(self.packdir, 'plug2.py'), 'w')
        plug2.write('# I do not have any pkgcore_plugins for you!\n')
        plug2.close()
        # Append it to the path
        sys.path.insert(0, self.dir)

    def tearDown(self):
        # pop the test module dir from path
        sys.path.pop(0)
        # and kill it
        shutil.rmtree(self.dir)
        # make sure we don't keep the sys.modules entries around
        sys.modules.pop('mod_testplug', None)
        sys.modules.pop('mod_testplug.plug', None)
        sys.modules.pop('mod_testplug.plug2', None)

    def _runit(self, method):
        plugin._cache = {}
        method()
        method()
        plugin._cache = {}
        method()
        method()

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
