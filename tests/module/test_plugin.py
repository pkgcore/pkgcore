import logging
import os
import shutil
import sys
import tempfile
from unittest import mock

from snakeoil.osutils import pjoin
from snakeoil.sequences import stable_unique

from pkgcore import plugin
from pkgcore.test import silence_logging


class LowPlug:
    priority = 1


class TestModules:

    def setup_method(self, method):
        self.dir = tempfile.mkdtemp()
        self.dir2 = tempfile.mkdtemp()

        # force plugin module to use package dir for cache dir by setting
        # system/user cache dirs to nonexistent paths
        self.patcher = mock.patch('pkgcore.plugin.const')
        const = self.patcher.start()
        const.SYSTEM_CACHE_PATH = pjoin(self.dir, 'nonexistent')
        const.USER_CACHE_PATH = pjoin(self.dir, 'nonexistent')

        # Set up some test modules for our use.
        self.packdir = pjoin(self.dir, 'mod_testplug')
        self.packdir2 = pjoin(self.dir2, 'mod_testplug')
        os.mkdir(self.packdir)
        os.mkdir(self.packdir2)
        with open(pjoin(self.packdir, '__init__.py'), 'w') as init:
            init.write('''
from pkgcore.plugins import extend_path

extend_path(__path__, __name__)
''')
        filename = pjoin(self.packdir, 'plug.py')
        with open(filename, 'w') as plug:
            plug.write('''
class DisabledPlug:
    disabled = True

class HighPlug:
    priority = 7

class LowPlug:
    priority = 1

low_plug = LowPlug()
high_plug = HighPlug()

pkgcore_plugins = {
    'plugtest': [
        DisabledPlug,
        high_plug,
        'module.test_plugin.LowPlug',
    ]
}
''')
        # Move the mtime 2 seconds into the past so the .pyc file has
        # a different mtime.
        st = os.stat(filename)
        os.utime(filename, (st.st_atime, st.st_mtime - 2))
        with open(pjoin(self.packdir, 'plug2.py'), 'w') as plug2:
            plug2.write('# I do not have any pkgcore_plugins for you!\n')
        with open(pjoin(self.packdir2, 'plug.py'), 'w') as plug:
            plug.write('''
# This file is later on sys.path than the plug.py in packdir, so it should
# not have any effect on the tests.

class HiddenPlug:
    priority = 8

pkgcore_plugins = {'plugtest': [HiddenPlug]}
''')
        # Append it to the path
        sys.path.insert(0, self.dir2)
        sys.path.insert(0, self.dir)

    def teardown_method(self):
        # stop mocked patcher
        self.patcher.stop()
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
        expected = stable_unique(
            pjoin(p, 'mod_testplug')
            for p in sys.path if os.path.isdir(p))
        assert expected == mod_testplug.__path__, \
            set(expected) ^ set(mod_testplug.__path__)

    def _runit(self, method):
        plugin._global_cache.clear()
        method()
        mtime = os.path.getmtime(pjoin(self.packdir, plugin.CACHE_FILENAME))
        method()
        plugin._global_cache.clear()
        method()
        method()
        assert mtime == \
            os.path.getmtime(pjoin(self.packdir, plugin.CACHE_FILENAME))
        # We cannot write this since it contains an unimportable plugin.
        assert not os.path.exists(pjoin(self.packdir2, plugin.CACHE_FILENAME))

    def _test_plug(self):
        import mod_testplug
        assert plugin.get_plugin('spork', mod_testplug) is None
        plugins = list(plugin.get_plugins('plugtest', mod_testplug))
        assert len(plugins) == 2, plugins
        plugin.get_plugin('plugtest', mod_testplug)
        assert 'HighPlug' == \
            plugin.get_plugin('plugtest', mod_testplug).__class__.__name__
        with open(pjoin(self.packdir, plugin.CACHE_FILENAME)) as f:
            lines = f.readlines()
        assert len(lines) == 3
        assert plugin.CACHE_HEADER + "\n" == lines[0]
        lines.pop(0)
        lines.sort()
        mtime = int(os.path.getmtime(pjoin(self.packdir, 'plug2.py')))
        assert f'plug2:{mtime}:\n' == lines[0]
        mtime = int(os.path.getmtime(pjoin(self.packdir, 'plug.py')))
        assert (
            f'plug:{mtime}:plugtest,7,1:plugtest,1,module.test_plugin.LowPlug:plugtest,0,0\n'
            == lines[1])

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
        assert 'mod_testplug.plug' in sys.modules, 'plug not loaded'
        assert 'mod_testplug.plug2' not in sys.modules, 'plug2 loaded'

    def test_no_unneeded_import(self):
        self._runit(self._test_no_unneeded_import)

    @silence_logging(logging.root)
    def test_cache_corruption(self):
        print(plugin.const)
        print('wheeeeee')
        import mod_testplug
        list(plugin.get_plugins('spork', mod_testplug))
        filename = pjoin(self.packdir, plugin.CACHE_FILENAME)
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
            pjoin(self.packdir, plugin.CACHE_FILENAME))
        plugin._global_cache.clear()
        self._test_plug()
        assert good_mtime == os.path.getmtime(pjoin(self.packdir, plugin.CACHE_FILENAME))
        assert good_mtime != corrupt_mtime

    def test_rewrite_on_remove(self):
        filename = pjoin(self.packdir, 'extra.py')
        plug = open(filename, 'w')
        try:
            plug.write('pkgcore_plugins = {"plugtest": [object()]}\n')
        finally:
            plug.close()

        plugin._global_cache.clear()
        import mod_testplug
        assert len(list(plugin.get_plugins('plugtest', mod_testplug))) == 3

        os.unlink(filename)

        plugin._global_cache.clear()
        self._test_plug()

    @silence_logging(logging.root)
    def test_priority_caching(self):
        plug3 = open(pjoin(self.packdir, 'plug3.py'), 'w')
        try:
            plug3.write('''
class LowPlug:
    priority = 6

pkgcore_plugins = {
    'plugtest': [LowPlug()],
}
''')
        finally:
            plug3.close()
        plug4 = open(pjoin(self.packdir, 'plug4.py'), 'w')
        try:
            plug4.write('''
# First file tried, only a disabled plugin.
class HighDisabledPlug:
    priority = 15
    disabled = True

pkgcore_plugins = {
    'plugtest': [HighDisabledPlug()],
}
''')
        finally:
            plug4.close()
        plug5 = open(pjoin(self.packdir, 'plug5.py'), 'w')
        try:
            plug5.write('''
# Second file tried, with a skipped low priority plugin.
class HighDisabledPlug:
    priority = 12
    disabled = True

class LowPlug:
    priority = 6

pkgcore_plugins = {
    'plugtest': [HighDisabledPlug(), LowPlug()],
}
''')
        finally:
            plug5.close()
        plug6 = open(pjoin(self.packdir, 'plug6.py'), 'w')
        try:
            plug6.write('''
# Not tried, bogus priority.
class BogusPlug:
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
        assert plug.high_plug == best_plug
        # Extra messages since getting all of sys.modules printed is annoying.
        assert 'mod_testplug.plug' in sys.modules, 'plug not loaded'
        assert 'mod_testplug.plug2' not in sys.modules, 'plug2 loaded'
        assert 'mod_testplug.plug3' not in sys.modules, 'plug3 loaded'
        assert 'mod_testplug.plug4' in sys.modules, 'plug4 not loaded'
        assert 'mod_testplug.plug5' in sys.modules, 'plug4 not loaded'
        assert 'mod_testplug.plug6' not in sys.modules, 'plug6 loaded'

    @silence_logging(logging.root)
    def test_header_change_invalidates_cache(self):
        # Write the cache
        plugin._global_cache.clear()
        import mod_testplug
        list(plugin.get_plugins('testplug', mod_testplug))

        # Modify the cache.
        filename = pjoin(self.packdir, plugin.CACHE_FILENAME)
        with open(filename) as f:
            cache = f.readlines()
        cache[0] = 'not really a pkgcore plugin cache\n'
        with open(filename, 'w') as f:
            f.write(''.join(cache))

        # And test if it is properly rewritten.
        plugin._global_cache.clear()
        self._test_plug()
