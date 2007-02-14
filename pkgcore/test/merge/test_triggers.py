# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.merge import triggers, const
from pkgcore.fs import fs, contents
from pkgcore.fs.livefs import gen_obj, scan
from pkgcore.util.currying import partial
from pkgcore.util.osutils import pjoin, ensure_dirs
from pkgcore.test import TestCase, mixins
import os, shutil, time
from math import floor, ceil


class fake_trigger(triggers.base):

    def __init__(self, **kwargs):
        self._called = []
        if isinstance(kwargs.get('_hooks', False), basestring):
            kwargs['_hooks'] = (kwargs['_hooks'],)
        for k, v in kwargs.iteritems():
            if callable(v):
                v = patrial(v, self)
            setattr(self, k, v)

    def trigger(self, *args):
        self._called.append(args)


class fake_engine(object):

    def __init__(self, **kwargs):
        self._triggers = []
        for k, v in kwargs.iteritems():
            if callable(v):
                v = partial(v, self)
            setattr(self, k, v)

    def add_trigger(self, hook_point, trigger, required_csets):
        if hook_point in getattr(self, "blocked_hooks", []):
            raise KeyError(hook_point)
        self._triggers.append((hook_point, trigger, required_csets))


class TestBase(TestCase):

    kls = fake_trigger
    
    def mk_trigger(self, kls=None, **kwargs):
        if kls is None:
            kls = self.kls
        return kls(**kwargs)

    def test_default_attrs(self):
        for x in ("required_csets", "_label", "_hooks", "_engine_types"):
            self.assertEqual(None, getattr(self.kls, x),
                msg="%s must exist and be None" % x)
        self.assertEqual(50, self.kls._priority)

    def test_label(self):
        self.assertEqual(self.mk_trigger().label, str(self.kls.__name__))
        self.assertEqual(fake_trigger().label, str(fake_trigger.__name__))
        self.assertEqual(fake_trigger(_label='foon').label, 'foon')

    def test_priority(self):
        self.assertEqual(fake_trigger(_priority=50).priority, 50)
        self.assertEqual(fake_trigger(_priority=10000).priority, 10000)
        self.assertEqual(fake_trigger(_priority=0).priority, 0)

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
        self.assertEqual(list(t.saved_mtimes),
            o)
        open(pjoin(self.dir, 'file'), 'w')
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
        open(pjoin(self.dir, 'bar'), 'w')
        self.assertTrue(t.check_state())

        # test dead sym filtering for stat.
        t.set_state(locs)
        self.assertEqual(sorted(t.saved_mtimes), o)
        self.assertFalse(t.check_state())
    
    def test_float_mtime(self):
        cur = os.stat_float_times()
        try:
            t = self.kls()
            t.set_state([self.dir])
            l = list(t.saved_mtimes)
            self.assertEqual(len(l), 1)
            l = l[0]
            self.assertTrue(isinstance(l.mtime, float),
                msg="mtime *must* be a float got %r" % l.mtime)
        finally:
            os.stat_float_times(cur)

    def test_race_protection(self):
        # note this isn't perfect- being a race, triggering it on 
        # demand is tricky.
        # hence the 10x loop; can trigger it pretty much each loop
        # for my 1ghz, so... it's a start.
        # the race specifically will only rear it's head on extremely
        # fast io (crazy hardware, or async mount), fs's lacking subsecond,
        # and just severely crappy chance.
        # faster the io actions, easier it is to trigger.
        cur = os.stat_float_times()
        try:
            t = self.kls()
            os.stat_float_times(True)
            for x in xrange(10):
                now = ceil(time.time()) + 1
                os.utime(self.dir, (now + 100, now + 100))
                t.set_state([self.dir])
                while now > ceil(time.time()):
                    t.set_state([self.dir])
                now, st_mtime = time.time(), os.stat(self.dir).st_mtime
                now, st_mtime = ceil(now), floor(st_mtime)
                self.assertTrue(now > st_mtime,
                    msg="%r must be > %r" % (now, st_mtime))
        finally:
            os.stat_float_times(cur)


def castrate_ldconfig(base_kls):
    class castrated_ldconfig(base_kls):

        def __init__(self, *args, **kwargs):
            self._passed_in_offset = []
            triggers.ldconfig.__init__(self, *args, **kwargs)
    
        def regen(self, offset):
            self._passed_in_offset.append(offset)

    return castrated_ldconfig


class Test_ldconfig(mixins.TempDirMixin, TestCase):

    # use the kls indirection for when *bsd version of ldconfig trigger
    # is derived; will be pretty much the same, sans the trigger call.
    kls = castrate_ldconfig(triggers.ldconfig)

    def setUp(self):
        mixins.TempDirMixin.setUp(self)
        self.reset_objs()

    def reset_objs(self):
        self.engine = fake_engine(offset=self.dir)
        self.trigger = self.kls()

    def assertPaths(self, expected, tested):
        expected = sorted(expected)
        tested = sorted(tested)
        self.assertEqual(expected, tested,
            msg="expected %r, got %r" % (expected, tested))

    def test_read_ld_so_conf(self):
        # test the defaults first.  should create etc and the file.
        self.assertPaths(self.trigger.read_ld_so_conf(self.dir),
            [pjoin(self.dir, x) for x in self.trigger.default_ld_path])
        o = gen_obj(pjoin(self.dir, 'etc'))
        self.assertEqual(o.mode, 0755)
        self.assertTrue(fs.isdir(o))
        self.assertTrue(os.path.exists(pjoin(self.dir, 'etc/ld.so.conf')))
        
        # test normal functioning.
        open(pjoin(self.dir, 'etc/ld.so.conf'), 'w').write("\n".join(
            ["/foon", "dar", "blarnsball", "#comment"]))
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
        open(pjoin(self.dir, "etc/ld.so.conf"), "w").write(
            "\n".join('/' + x for x in dirs))
        # force directory mtime to 1s less.
        past = time.time() - 10.0
        if mkdirs:
            for x in dirs:
                ensure_dirs(pjoin(self.dir, x))
                os.utime(pjoin(self.dir, x), (past, past))

        self.trigger = self.kls()
        self.engine.phase = 'pre_%s' % hook
        self.engine.mode = mode
        self.trigger(self.engine, {})
        self.assertFalse(self.trigger._passed_in_offset)
        resets = set()
        for x in touches:
            fp = pjoin(self.dir, x.lstrip('/'))
            open(pjoin(fp), "w")
            if same_mtime:
                os.utime(fp, (past, past))
                resets.add(os.path.dirname(fp))

        for x in resets:
            os.utime(x, (past, past))

        self.engine.phase = 'post_%s' % hook
        self.trigger(self.engine, {})

        if ran:
            self.assertEqual(len(self.trigger._passed_in_offset), 1)
        else:
            self.assertEqual(len(self.trigger._passed_in_offset), 0)

    def test_trigger(self):
        # ensure it doesn't explode for missing dirs.
        self.assertTrigger([], False, mkdirs=False)
        self.assertTrigger([], False)
        self.assertTrigger(['test-lib/foon'], True)
        self.assertTrigger(['test-lib/foon'], False, same_mtime=True)
