import os
import shutil
import time
from functools import partial
from math import ceil, floor

import pytest
from snakeoil import process
from snakeoil.currying import post_curry
from snakeoil.osutils import ensure_dirs, normpath, pjoin
from snakeoil.test import TestCase, mixins

from pkgcore.fs import fs
from pkgcore.fs.contents import contentsSet
from pkgcore.fs.livefs import gen_obj, scan
from pkgcore.merge import const, triggers

from .util import fake_engine, fake_reporter, fake_trigger


def _render_msg(func, msg, *args, **kwargs):
    func(msg % (args if args else kwargs))

def make_fake_reporter(**kwargs):
    kwargs = dict((key, partial(_render_msg, val))
                  for key, val in kwargs.items())
    return fake_reporter(**kwargs)

class TestBase(TestCase):

    kls = fake_trigger

    def mk_trigger(self, kls=None, **kwargs):
        if kls is None:
            kls = self.kls
        return kls(**kwargs)

    def test_default_attrs(self):
        for x in ("required_csets", "_label", "_hooks", "_engine_types"):
            self.assertEqual(
                None, getattr(self.kls, x),
                msg=f"{x} must exist and be None")
        self.assertEqual(50, self.kls.priority)

    def test_label(self):
        self.assertEqual(self.mk_trigger().label, str(self.kls.__name__))
        self.assertEqual(fake_trigger().label, str(fake_trigger.__name__))
        self.assertEqual(fake_trigger(_label='foon').label, 'foon')

    def test_localize(self):
        o = self.mk_trigger()
        self.assertEqual(o, o.localize(None))

    def test_get_required_csets(self):
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            None), None)
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            1), None)
        self.assertEqual(fake_trigger(required_csets=None).get_required_csets(
            ""), None)
        o = fake_trigger(required_csets={"foo":["dar"], "bar":1})
        self.assertEqual(o.get_required_csets("foo"), ["dar"])
        self.assertEqual(o.get_required_csets("bar"), 1)
        self.assertEqual(fake_trigger(required_csets=("dar", "foo"))
            .get_required_csets("bar"), ("dar", "foo"))
        self.assertEqual(fake_trigger(required_csets=())
            .get_required_csets(""), ())

    def test_register(self):
        engine = fake_engine(mode=1)
        self.assertRaises(TypeError, self.mk_trigger(mode=1).register, engine)
        self.assertRaises(TypeError, self.mk_trigger(mode=1, _hooks=2).register,
            engine)
        self.assertFalse(engine._triggers)

        # shouldn't puke.
        o = self.mk_trigger(mode=1, _hooks=("2"))
        o.register(engine)
        self.assertEqual(engine._triggers, [('2', o, None)])
        engine._triggers = []

        # verify it's treating "all csets" differently from "no csets"
        o = self.mk_trigger(mode=1, _hooks=("2"), required_csets=())
        o.register(engine)
        self.assertEqual(engine._triggers, [('2', o, ())])

        # should handle keyerror thrown from the engine for missing hooks.
        engine = fake_engine(mode=1, blocked_hooks=("foon", "dar"))
        self.mk_trigger(mode=1, _hooks="foon").register(engine)
        self.mk_trigger(mode=1, _hooks=("foon", "dar")).register(engine)
        self.assertFalse(engine._triggers)

        o = self.mk_trigger(mode=1, _hooks=("foon", "bar"), required_csets=(3,))
        o.register(engine)
        self.assertEqual(engine._triggers, [('bar', o, (3,))])
        engine._triggers = []
        o = self.mk_trigger(mode=1, _hooks="bar", required_csets=None)
        o.register(engine)
        self.assertEqual(engine._triggers, [('bar', o, None)])

    def test_call(self):
        # test "I want all csets"
        def get_csets(required_csets, csets, fallback=None):
            o = self.mk_trigger(required_csets={1:required_csets, 2:fallback},
                mode=(1,))
            engine = fake_engine(csets=csets, mode=1)
            o(engine, csets)
            self.assertEqual([x[0] for x in o._called],
                [engine]*len(o._called))
            return [list(x[1:]) for x in o._called]

        d = object()
        self.assertEqual(get_csets(None, d, [1]), [[d]],
            msg="raw csets mapping should be passed through without conversion"
                " for required_csets=None")

        self.assertEqual(get_csets([1,2], {1:1,2:2}), [[1, 2]],
            msg="basic mapping through failed")
        self.assertEqual(get_csets([], {}), [[]],
            msg="for no required csets, must have no args passed")


class test_module(TestCase):

    def test_constants(self):
        self.assertEqual(sorted([const.REPLACE_MODE, const.UNINSTALL_MODE]),
            sorted(triggers.UNINSTALLING_MODES))
        self.assertEqual(sorted([const.REPLACE_MODE, const.INSTALL_MODE]),
            sorted(triggers.INSTALLING_MODES))


class Test_mtime_watcher(mixins.TempDirMixin, TestCase):

    kls = triggers.mtime_watcher

    def test_identification(self):
        o = [gen_obj(self.dir)]
        t = self.kls()
        t.set_state([self.dir])
        self.assertEqual(list(t.saved_mtimes), o)
        open(pjoin(self.dir, 'file'), 'w').close()
        t.set_state([self.dir, pjoin(self.dir, 'file')])
        self.assertEqual(list(t.saved_mtimes), o)
        loc = pjoin(self.dir, 'dir')
        os.mkdir(loc)
        o.append(gen_obj(pjoin(self.dir, 'dir')))
        o.sort()
        t.set_state([x.location for x in o])
        self.assertEqual(sorted(t.saved_mtimes), o)

        # test syms.
        src = pjoin(self.dir, 'dir2')
        os.mkdir(src)
        loc = pjoin(self.dir, 'foo')
        os.symlink(src, loc)
        locs = [x.location for x in o]

        # insert a crap location to ensure it handles it.
        locs.append(pjoin(self.dir, "asdfasdfasdfasfdasdfasdfasdfasdf"))

        locs.append(src)
        i = gen_obj(src, stat=os.stat(src))
        o.append(i)
        o.sort()
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)
        locs[-1] = loc
        o.remove(i)
        i = i.change_attributes(location=loc)
        o.append(i)
        o.sort()
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)

        o.remove(i)
        os.rmdir(src)

        # check stat_func usage; if lstat, the sym won't be derefed,
        # thus ignored.
        t.set_state(locs, stat_func=os.lstat)
        self.assertEqual(sorted(t.saved_mtimes), o)
        open(pjoin(self.dir, 'bar'), 'w').close()
        self.assertTrue(t.check_state())

        # test dead sym filtering for stat.
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)
        self.assertFalse(t.check_state())

    def test_float_mtime(self):
        t = self.kls()
        t.set_state([self.dir])
        l = list(t.saved_mtimes)
        self.assertEqual(len(l), 1)
        l = l[0]
        # mtime *must* be a float.
        self.assertInstance(l.mtime, float)

    def test_race_protection(self):
        # note this isn't perfect- being a race, triggering it on
        # demand is tricky.
        # hence the 10x loop; can trigger it pretty much each loop
        # for my 1ghz, so... it's a start.
        # the race specifically will only rear its head on extremely
        # fast io (crazy hardware, or async mount), fs's lacking subsecond,
        # and just severely crappy chance.
        # faster the io actions, easier it is to trigger.
        t = self.kls()
        for x in range(100):
            now = ceil(time.time()) + 1
            os.utime(self.dir, (now + 100, now + 100))
            t.set_state([self.dir])
            now, st_mtime = time.time(), os.stat(self.dir).st_mtime
            now, st_mtime = ceil(now), floor(st_mtime)
            self.assertTrue(
                now > st_mtime,
                msg=f"{now!r} must be > {st_mtime!r}")


def castrate_trigger(base_kls, **kwargs):
    class castrated_trigger(base_kls):

        enable_regen = False
        def __init__(self, *args2, **kwargs2):
            self._passed_in_args = []
            base_kls.__init__(self, *args2, **kwargs2)

        def regen(self, *args):
            self._passed_in_args.append(list(args))
            if self.enable_regen:
                return base_kls.regen(self, *args)
            return []

        locals().update(kwargs)

    return castrated_trigger


class trigger_mixin(mixins.TempDirMixin):

    def setUp(self):
        mixins.TempDirMixin.setUp(self)
        self.reset_objects()

    def reset_objects(self, mode=const.INSTALL_MODE):
        self.engine = fake_engine(offset=self.dir, mode=mode)
        self.trigger = self.kls()

    def assertPaths(self, expected, tested):
        expected = sorted(expected)
        tested = sorted(tested)
        self.assertEqual(
            expected, tested,
            msg="expected {expected!}, got {tested!r}")


class Test_ldconfig(trigger_mixin, TestCase):

    # use the kls indirection for when *bsd version of ldconfig trigger
    # is derived; will be pretty much the same, sans the trigger call.

    kls = castrate_trigger(triggers.ldconfig)

    def test_read_ld_so_conf(self):
        # test the defaults first.  should create etc and the file.
        self.assertPaths(self.trigger.read_ld_so_conf(self.dir),
            [pjoin(self.dir, x) for x in self.trigger.default_ld_path])
        o = gen_obj(pjoin(self.dir, 'etc'))
        self.assertEqual(o.mode, 0o755)
        self.assertTrue(fs.isdir(o))
        self.assertTrue(os.path.exists(pjoin(self.dir, 'etc/ld.so.conf')))

        # test normal functioning.
        with open(pjoin(self.dir, 'etc/ld.so.conf'), 'w') as f:
            f.write("\n".join(["/foon", "dar", "blarnsball", "#comment"]))
        self.assertPaths(self.trigger.read_ld_so_conf(self.dir),
            [pjoin(self.dir, x) for x in ["foon", "dar", "blarnsball"]])

    def assertTrigger(self, touches, ran, dirs=['test-lib', 'test-lib2'],
        hook='merge', mode=const.INSTALL_MODE, mkdirs=True, same_mtime=False):

        # wipe whats there.
        for x in scan(self.dir).iterdirs():
            if x.location == self.dir:
                continue
            shutil.rmtree(x.location)
        for x in scan(self.dir).iterdirs(True):
            os.unlink(x.location)

        ensure_dirs(pjoin(self.dir, "etc"))
        with open(pjoin(self.dir, "etc/ld.so.conf"), "w") as f:
            f.write("\n".join('/' + x for x in dirs))
        # force directory mtime to 1s less.
        past = time.time() - 10.0
        if mkdirs:
            for x in dirs:
                ensure_dirs(pjoin(self.dir, x))
                os.utime(pjoin(self.dir, x), (past, past))

        self.reset_objects()
        self.engine.phase = f'pre_{hook}'
        self.engine.mode = mode
        self.trigger(self.engine, {})
        self.assertFalse(self.trigger._passed_in_args)
        resets = set()
        for x in touches:
            fp = pjoin(self.dir, x.lstrip('/'))
            open(pjoin(fp), "w").close()
            if same_mtime:
                os.utime(fp, (past, past))
                resets.add(os.path.dirname(fp))

        for x in resets:
            os.utime(x, (past, past))

        self.engine.phase = f'post_{hook}'
        self.trigger(self.engine, {})

        self.assertEqual([[getattr(x, 'offset', None) for x in y]
            for y in self.trigger._passed_in_args],
            [[self.dir]])

    def test_trigger(self):
        # ensure it doesn't explode for missing dirs.
        #self.assertTrigger([], False, mkdirs=False)
        #self.assertTrigger([], False)
        self.assertTrigger(['test-lib/foon'], True)
        self.assertTrigger(['test-lib/foon'], False, same_mtime=True)


class TestInfoRegen(trigger_mixin, TestCase):

    raw_kls = triggers.InfoRegen
    @property
    def kls(self):
        return castrate_trigger(self.raw_kls, locations=['/'])

    info_data = \
"""INFO-DIR-SECTION Network Applications
START-INFO-DIR-ENTRY
* Wget: (wget).         The non-interactive network downloader.
END-INFO-DIR-ENTRY
"""

    def reset_objects(self, **kwargs):
        trigger_mixin.reset_objects(self, **kwargs)
        self.trigger.location = [self.dir]

    def test_binary_path(self):
        existing = os.environ.get("PATH", self)
        try:
            try:
                path = process.find_binary('install-info')
            except process.CommandNotFound:
                path = None
            self.assertEqual(path, self.trigger.get_binary_path())
            if path is not self:
                os.environ["PATH"] = ""
                self.assertEqual(None, self.trigger.get_binary_path())
        finally:
            if existing is self:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = existing

    def test_regen(self):
        o = self.raw_kls()
        path = o.get_binary_path()
        if path is None:
            pytest.skip("can't verify regen behaviour due to install-info not being available")
        # test it without the directory existing.
        self.assertEqual(list(o.regen(path, pjoin(self.dir, 'foo'))), [])
        self.assertFalse(os.path.exists(pjoin(self.dir, 'foo')))
        with open(pjoin(self.dir, "foo.info"), 'w') as f:
            f.write(self.info_data)
        # no issues.
        self.assertEqual(list(o.regen(path, self.dir)), [])
        self.assertTrue(os.path.exists(pjoin(self.dir, 'dir')),
            msg="info dir file wasn't created")

        # drop the last line, verify it returns that file.
        with open(pjoin(self.dir, "foo2.info"), 'w') as f:
            f.write('\n'.join(self.info_data.splitlines()[:-1]))
        # should ignore \..* files
        open(pjoin(self.dir, ".foo.info"), 'w').close()
        os.unlink(pjoin(self.dir, 'dir'))
        self.assertEqual(list(o.regen(path, self.dir)),
            [pjoin(self.dir, 'foo2.info')])
        self.assertTrue(os.path.exists(pjoin(self.dir, 'dir')),
            msg="info dir file wasn't created")

    def run_trigger(self, phase, expected_regen=[]):
        l = []
        self.engine.observer = make_fake_reporter(warn=l.append)
        self.trigger._passed_in_args = []
        self.engine.phase = phase
        self.trigger(self.engine, {})
        self.assertEqual(list(map(normpath, (x[1] for x in self.trigger._passed_in_args))),
            list(map(normpath, expected_regen)))
        return l

    def test_trigger(self):
        if self.raw_kls().get_binary_path() is None:
            pytest.skip("can't verify regen behaviour due to install-info not being available")

        cur = os.environ.get("PATH", self)
        try:
            os.environ.pop("PATH", None)
            # shouldn't run if the binary is missing
            # although it should warn, and this code will explode when it does.
            self.engine.phase = 'post_merge'
            self.assertEqual(None, self.trigger(self.engine, {}))
        finally:
            if cur is not self:
                os.environ["PATH"] = cur

        # verify it runs when dir is missing.
        # doesn't create the file since no info files.
        self.reset_objects()
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))

        # add an info, and verify it generated.
        with open(pjoin(self.dir, 'foo.info'), 'w') as f:
            f.write(self.info_data)
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))

        # verify it doesn't; mtime is fine
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', []))

        # verify it handles quoting properly, and that it ignores
        # complaints about duplicates.
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        with open(pjoin(self.dir, "blaidd drwg.info"), "w") as f:
            f.write(self.info_data)
        self.assertFalse(self.run_trigger('post_merge', [self.dir]))

        # verify it passes back failures.
        self.reset_objects()
        self.trigger.enable_regen = True
        self.assertFalse(self.run_trigger('pre_merge', []))
        with open(pjoin(self.dir, "tiza grande.info"), "w") as f:
            f.write('\n'.join(self.info_data.splitlines()[:-1]))
        l = self.run_trigger('post_merge', [self.dir])
        self.assertEqual(len(l), 1)
        self.assertIn('tiza grande.info', l[0])

        # verify it holds off on info regen till after unmerge for replaces.
        self.reset_objects(mode=const.REPLACE_MODE)
        self.assertFalse(self.run_trigger('pre_merge', []))
        self.assertFalse(self.run_trigger('post_merge', []))
        self.assertFalse(self.run_trigger('pre_unmerge', []))
        os.unlink(pjoin(self.dir, "tiza grande.info"))
        self.assertFalse(self.run_trigger('post_unmerge', [self.dir]))


class single_attr_change_base:

    kls = triggers.fix_uid_perms
    attr = None

    bad_val = 1

    @staticmethod
    def good_val(val):
        return 2

    def test_metadata(self):
        self.assertEqual(self.kls._engine_types, triggers.INSTALLING_MODES)
        self.assertEqual(self.kls.required_csets, ('new_cset',))
        self.assertEqual(self.kls._hooks, ('pre_merge',))

    @property
    def trigger(self):
        return self.kls(1, 2)

    def assertContents(self, cset=()):
        orig = sorted(cset)
        new = contentsSet(orig)
        self.trigger(fake_engine(mode=const.INSTALL_MODE),
            {'new_cset':new})
        new = sorted(new)
        self.assertEqual(len(orig), len(new))
        for x, y in zip(orig, new):
            self.assertEqual(orig.__class__, new.__class__)
            for attr in x.__attrs__:
                if self.attr == attr:
                    val = getattr(x, attr)
                    if self.bad_val is not None and val == self.bad_val:
                        self.assertEqual(self.good_val(val), getattr(y, attr))
                    else:
                        self.assertEqual(self.good_val(val), getattr(y, attr))
                elif attr != 'chksums':
                    # abuse self as unique singleton.
                    self.assertEqual(getattr(x, attr, self),
                        getattr(y, attr, self))

    def test_trigger(self):
        self.assertContents()
        self.assertContents([fs.fsFile("/foon", mode=0o644, uid=2, gid=1,
            strict=False)])
        self.assertContents([fs.fsFile("/foon", mode=0o646, uid=1, gid=1,
            strict=False)])
        self.assertContents([fs.fsFile("/foon", mode=0o4766, uid=1, gid=2,
            strict=False)])
        self.assertContents([fs.fsFile("/blarn", mode=0o2700, uid=2, gid=2,
            strict=False),
            fs.fsDir("/dir", mode=0o500, uid=2, gid=2, strict=False)])
        self.assertContents([fs.fsFile("/blarn", mode=0o2776, uid=2, gid=2,
            strict=False),
            fs.fsDir("/dir", mode=0o2777, uid=1, gid=2, strict=False)])
        self.assertContents([fs.fsFile("/blarn", mode=0o6772, uid=2, gid=2,
            strict=False),
            fs.fsDir("/dir", mode=0o4774, uid=1, gid=1, strict=False)])


class Test_fix_uid_perms(single_attr_change_base, TestCase):

    kls = triggers.fix_uid_perms
    attr = 'uid'


class Test_fix_gid_perms(single_attr_change_base, TestCase):

    kls = triggers.fix_gid_perms
    attr = 'gid'


class Test_fix_set_bits(single_attr_change_base, TestCase):

    kls = triggers.fix_set_bits
    trigger = property(lambda self:self.kls())
    attr = 'mode'

    @staticmethod
    def good_val(val):
        if val & 0o6000 and val & 0o002:
            return val & ~0o6002
        return val


class Test_detect_world_writable(single_attr_change_base, TestCase):

    kls = triggers.detect_world_writable
    _trigger_override = None

    attr = 'mode'

    @property
    def trigger(self):
        if self._trigger_override is None:
            return self.kls(fix_perms=True)
        return self._trigger_override()

    def good_val(self, val):
        self.assertEqual(self._trigger_override, None,
            msg="bug in test code; good_val should not be invoked when a "
                "trigger override is in place.")
        return val & ~0o002

    def test_lazyness(self):
        # ensure it doesn't even look if it won't make noise, and no reporter
        # cset is intentionally *not* a contentset; it'll explode it it tries
        # to access it.
        self.kls().trigger(fake_engine(), None)
        # now verify that the explosion would occur if either settings are on.
        self.assertRaises((AttributeError, TypeError),
            self.kls().trigger, fake_engine(observer=object()), None)
        self.assertRaises((AttributeError, TypeError),
            self.kls(fix_perms=True).trigger, fake_engine(), None)

    def test_observer_warn(self):
        warnings = []
        engine = fake_engine(observer=make_fake_reporter(warn=warnings.append))

        self._trigger_override = self.kls()

        def run(fs_objs, fix_perms=False):
            self.kls(fix_perms=fix_perms).trigger(engine,
                contentsSet(fs_objs))

        run([fs.fsFile('/foon', mode=0o770, strict=False)])
        self.assertFalse(warnings)
        run([fs.fsFile('/foon', mode=0o772, strict=False)])
        self.assertEqual(len(warnings), 1)
        self.assertIn('/foon', warnings[0])

        warnings[:] = []

        run([fs.fsFile('/dar', mode=0o776, strict=False),
            fs.fsFile('/bar', mode=0o776, strict=False),
            fs.fsFile('/far', mode=0o770, strict=False)])

        self.assertEqual(len(warnings), 2)
        self.assertIn('/dar', ' '.join(warnings))
        self.assertIn('/bar', ' '.join(warnings))
        self.assertNotIn('/far', ' '.join(warnings))


class TestPruneFiles(TestCase):

    kls = triggers.PruneFiles

    def test_metadata(self):
        self.assertEqual(self.kls.required_csets, ('new_cset',))
        self.assertEqual(self.kls._hooks, ('pre_merge',))
        self.assertEqual(self.kls._engine_types, triggers.INSTALLING_MODES)

    def test_it(self):
        orig = contentsSet([
            fs.fsFile('/cheddar', strict=False),
            fs.fsFile('/sporks-suck', strict=False),
            fs.fsDir('/foons-rule', strict=False),
            fs.fsDir('/mango', strict=False)
        ])

        engine = fake_engine(mode=const.INSTALL_MODE)
        def run(func):
            new = contentsSet(orig)
            self.kls(func)(engine, {'new_cset':new})
            return new

        self.assertEqual(orig, run(lambda s:False))
        self.assertEqual([], run(post_curry(isinstance, fs.fsDir)).dirs())
        self.assertEqual(sorted(orig.files()),
            sorted(run(post_curry(isinstance, fs.fsDir)).dirs(True)))

        # check noisyness.
        info = []
        engine = fake_engine(observer=make_fake_reporter(info=info.append),
            mode=const.REPLACE_MODE)

        run(lambda s:False)
        self.assertFalse(info)
        run(post_curry(isinstance, fs.fsDir))
        self.assertEqual(len(info), 2)

        # ensure only the relevant files show.
        self.assertNotIn('/cheddar', ' '.join(info))
        self.assertNotIn('/sporks-suck', ' '.join(info))
        self.assertIn('/foons-rule', ' '.join(info))
        self.assertIn('/mango', ' '.join(info))
