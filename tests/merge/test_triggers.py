import os
import sys
import textwrap
import time
from functools import partial
from math import ceil, floor

import pytest
from pkgcore.fs import fs
from pkgcore.fs.contents import contentsSet
from pkgcore.fs.livefs import gen_obj
from pkgcore.merge import const, triggers
from snakeoil import process
from snakeoil.contexts import os_environ
from snakeoil.currying import post_curry
from snakeoil.osutils import ensure_dirs, normpath

from .util import fake_engine, fake_reporter, fake_trigger


def _render_msg(func, msg, *args, **kwargs):
    func(msg % (args if args else kwargs))

def make_fake_reporter(**kwargs):
    kwargs = dict((key, partial(_render_msg, val))
                  for key, val in kwargs.items())
    return fake_reporter(**kwargs)

class TestBase:

    kls = fake_trigger

    def mk_trigger(self, kls=None, **kwargs):
        if kls is None:
            kls = self.kls
        return kls(**kwargs)

    def test_default_attrs(self):
        for x in ("required_csets", "_label", "_hooks", "_engine_types"):
            assert getattr(self.kls, x) is None, f"{x} must exist and be None"
        assert self.kls.priority == 50

    def test_label(self):
        assert self.mk_trigger().label == str(self.kls.__name__)
        assert fake_trigger().label == str(fake_trigger.__name__)
        assert fake_trigger(_label='foon').label == 'foon'

    def test_localize(self):
        o = self.mk_trigger()
        assert o == o.localize(None)

    def test_get_required_csets(self):
        assert fake_trigger(required_csets=None).get_required_csets(None) is None
        assert fake_trigger(required_csets=None).get_required_csets(1) is None
        assert fake_trigger(required_csets=None).get_required_csets("") is None
        o = fake_trigger(required_csets={"foo":["dar"], "bar":1})
        assert o.get_required_csets("foo") == ["dar"]
        assert o.get_required_csets("bar") == 1
        assert fake_trigger(required_csets=("dar", "foo")).get_required_csets("bar") == ("dar", "foo")
        assert fake_trigger(required_csets=()).get_required_csets("") == ()

    def test_register(self):
        engine = fake_engine(mode=1)
        with pytest.raises(TypeError):
            self.mk_trigger(mode=1).register(engine)
        with pytest.raises(TypeError):
            self.mk_trigger(mode=1, _hooks=2).register(engine)
        assert not engine._triggers

        # shouldn't puke.
        o = self.mk_trigger(mode=1, _hooks=("2"))
        o.register(engine)
        assert engine._triggers == [('2', o, None)]
        engine._triggers = []

        # verify it's treating "all csets" differently from "no csets"
        o = self.mk_trigger(mode=1, _hooks=("2"), required_csets=())
        o.register(engine)
        assert engine._triggers == [('2', o, ())]

        # should handle keyerror thrown from the engine for missing hooks.
        engine = fake_engine(mode=1, blocked_hooks=("foon", "dar"))
        self.mk_trigger(mode=1, _hooks="foon").register(engine)
        self.mk_trigger(mode=1, _hooks=("foon", "dar")).register(engine)
        assert not engine._triggers

        o = self.mk_trigger(mode=1, _hooks=("foon", "bar"), required_csets=(3,))
        o.register(engine)
        assert engine._triggers == [('bar', o, (3,))]
        engine._triggers = []
        o = self.mk_trigger(mode=1, _hooks="bar", required_csets=None)
        o.register(engine)
        assert engine._triggers == [('bar', o, None)]

    def test_call(self):
        # test "I want all csets"
        def get_csets(required_csets, csets, fallback=None):
            o = self.mk_trigger(required_csets={1:required_csets, 2:fallback},
                mode=(1,))
            engine = fake_engine(csets=csets, mode=1)
            o(engine, csets)
            assert [x[0] for x in o._called] == [engine]*len(o._called)
            return [list(x[1:]) for x in o._called]

        d = object()
        assert get_csets(None, d, [1]) == [[d]], \
            "raw csets mapping should be passed through without conversion" \
            " for required_csets=None"

        assert get_csets([1,2], {1: 1,2: 2}) == [[1, 2]],"basic mapping through failed"
        assert get_csets([], {}) == [[]], "for no required csets, must have no args passed"


def test_module_constants():
    assert {const.REPLACE_MODE, const.UNINSTALL_MODE} == set(triggers.UNINSTALLING_MODES)
    assert {const.REPLACE_MODE, const.INSTALL_MODE} == set(triggers.INSTALLING_MODES)


class Test_mtime_watcher:

    kls = triggers.mtime_watcher

    def test_identification(self, tmp_path):
        o = [gen_obj(str(tmp_path))]
        t = self.kls()
        t.set_state([str(tmp_path)])
        assert list(t.saved_mtimes) == o
        (tmp_path / 'file').touch()
        t.set_state([str(tmp_path), str(tmp_path / 'file')])
        assert list(t.saved_mtimes) == o
        os.mkdir(loc := str(tmp_path / 'dir'))
        o.append(gen_obj(loc))
        o.sort()
        t.set_state([x.location for x in o])
        assert sorted(t.saved_mtimes) == o

        # test syms.
        os.mkdir(src := str(tmp_path / 'dir2'))
        os.symlink(src, loc := str(tmp_path / 'foo'))
        locs = [x.location for x in o]

        # insert a crap location to ensure it handles it.
        locs.append(str(tmp_path / "asdfasdfasdfasfdasdfasdfasdfasdf"))

        locs.append(src)
        i = gen_obj(src, stat=os.stat(src))
        o.append(i)
        o.sort()
        t.set_state(locs)
        assert sorted(t.saved_mtimes) == o
        locs[-1] = loc
        o.remove(i)
        i = i.change_attributes(location=loc)
        o.append(i)
        o.sort()
        t.set_state(locs)
        assert sorted(t.saved_mtimes) == o

        o.remove(i)
        os.rmdir(src)

        # check stat_func usage; if lstat, the sym won't be derefed,
        # thus ignored.
        t.set_state(locs, stat_func=os.lstat)
        assert sorted(t.saved_mtimes) == o
        (tmp_path / 'bar').touch()
        assert t.check_state()

        # test dead sym filtering for stat.
        t.set_state(locs)
        assert sorted(t.saved_mtimes) == o
        assert not t.check_state()

    def test_float_mtime(self, tmp_path):
        t = self.kls()
        t.set_state([str(tmp_path)])
        l = list(t.saved_mtimes)
        assert len(l) == 1
        l = l[0]
        # mtime *must* be a float.
        assert isinstance(l.mtime, float)

    def test_race_protection(self, tmp_path):
        # note this isn't perfect- being a race, triggering it on
        # demand is tricky.
        # hence the 10x loop; can trigger it pretty much each loop
        # for my 1ghz, so... it's a start.
        # the race specifically will only rear its head on extremely
        # fast io (crazy hardware, or async mount), fs's lacking subsecond,
        # and just severely crappy chance.
        # faster the io actions, easier it is to trigger.
        t = self.kls()
        for _ in range(100):
            now = ceil(time.time()) + 1
            os.utime(tmp_path, (now + 100, now + 100))
            t.set_state([str(tmp_path)])
            now, st_mtime = time.time(), os.stat(tmp_path).st_mtime
            now, st_mtime = ceil(now), floor(st_mtime)
            assert now > st_mtime


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


class trigger_mixin:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.dir = str(tmp_path)
        self.reset_objects()

    def reset_objects(self, mode=const.INSTALL_MODE):
        self.engine = fake_engine(offset=self.dir, mode=mode)
        self.trigger = self.kls()


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='supported on Linux only')
class Test_ldconfig(trigger_mixin):

    # use the kls indirection for when *bsd version of ldconfig trigger
    # is derived; will be pretty much the same, sans the trigger call.

    kls = castrate_trigger(triggers.ldconfig)

    def test_read_ld_so_conf(self, tmp_path):
        # test the defaults first.  should create etc and the file.
        assert set(self.trigger.read_ld_so_conf(str(tmp_path))) == {str(tmp_path / x) for x in self.trigger.default_ld_path}
        o = gen_obj(str(tmp_path / 'etc'))
        assert o.mode == 0o755
        assert fs.isdir(o)
        assert (tmp_path / 'etc/ld.so.conf').exists()

        # test normal functioning.
        (tmp_path / 'etc/ld.so.conf').write_text("\n".join(("/foon", "dar", "blarnsball", "#comment")))
        assert set(self.trigger.read_ld_so_conf(str(tmp_path))) == {str(tmp_path / x) for x in ("foon", "dar", "blarnsball")}

    @pytest.mark.parametrize(("touches", "mkdirs", "same_mtime"), (
        # ensure it doesn't explode for missing dirs.
        ([], False, False),
        ([], True, False),

        (['test-lib/foon'], True, False),
        (['test-lib/foon'], True, True),
    ))
    def test_trigger(self, tmp_path, touches, mkdirs, same_mtime):
        dirs=['test-lib', 'test-lib2']

        ensure_dirs(tmp_path / "etc")
        (tmp_path / "etc/ld.so.conf").write_text("\n".join('/' + x for x in dirs))
        # force directory mtime to 1s less.
        past = time.time() - 10.0
        if mkdirs:
            for x in dirs:
                ensure_dirs(tmp_path / x)
                os.utime(tmp_path / x, (past, past))

        self.reset_objects()
        self.engine.phase = 'pre_merge'
        self.engine.mode = const.INSTALL_MODE
        self.trigger(self.engine, {})
        assert not self.trigger._passed_in_args

        resets = set()
        for x in touches:
            (fp := tmp_path / x.lstrip('/')).touch()
            if same_mtime:
                os.utime(fp, (past, past))
                resets.add(fp.parent)
        for x in resets:
            os.utime(x, (past, past))

        self.engine.phase = 'post_merge'
        self.trigger(self.engine, {})

        assert [[getattr(x, 'offset', None) for x in y] for y in self.trigger._passed_in_args] == [[str(tmp_path)]]


class TestInfoRegen(trigger_mixin):

    raw_kls = triggers.InfoRegen

    @property
    def kls(self):
        return castrate_trigger(self.raw_kls, locations=['/'])

    info_data = textwrap.dedent("""\
        INFO-DIR-SECTION Network Applications
        START-INFO-DIR-ENTRY
        * Wget: (wget).         The non-interactive network downloader.
        END-INFO-DIR-ENTRY
    """)

    def reset_objects(self, **kwargs):
        trigger_mixin.reset_objects(self, **kwargs)
        self.trigger.location = [self.dir]

    def test_binary_path(self):
        try:
            path = process.find_binary('install-info')
        except process.CommandNotFound:
            path = None
        assert path == self.trigger.get_binary_path()

        with os_environ("PATH"):
            assert self.trigger.get_binary_path() is None

    @pytest.mark.skipif(triggers.InfoRegen().get_binary_path() is None, reason="can't verify regen behavior due to install-info not being available")
    def test_regen(self, tmp_path):
        o = self.raw_kls()
        path = o.get_binary_path()
        # test it without the directory existing.
        assert not list(o.regen(path, str(tmp_path / 'foo')))
        assert not (tmp_path / 'foo').exists()
        (tmp_path / 'foo.info').write_text(self.info_data)
        # no issues.
        assert not list(o.regen(path, str(tmp_path)))
        assert (tmp_path / 'dir').exists(), "info dir file wasn't created"

        # drop the last line, verify it returns that file.
        (tmp_path / 'foo2.info').write_text('\n'.join(self.info_data.splitlines()[:-1]))
        # should ignore \..* files
        (tmp_path / ".foo.info").touch()
        (tmp_path / "dir").unlink()
        assert list(o.regen(path, self.dir)) == [str(tmp_path / 'foo2.info')]
        assert (tmp_path / 'dir').exists(), "info dir file wasn't created"

    def run_trigger(self, phase, expected_regen=()):
        l = []
        self.engine.observer = make_fake_reporter(warn=l.append)
        self.trigger._passed_in_args = []
        self.engine.phase = phase
        self.trigger(self.engine, {})
        assert list(map(normpath, (x[1] for x in self.trigger._passed_in_args))) == list(map(normpath, expected_regen))
        return l

    @pytest.mark.skipif(triggers.InfoRegen().get_binary_path() is None, reason="can't verify regen behavior due to install-info not being available")
    def test_trigger(self, tmp_path):

        with os_environ("PATH"):
            self.engine.phase = 'post_merge'
            assert self.trigger(self.engine, {}) is None

        # verify it runs when dir is missing.
        # doesn't create the file since no info files.
        self.reset_objects()
        assert not self.run_trigger('pre_merge', [])
        assert not self.run_trigger('post_merge', [self.dir])

        # add an info, and verify it generated.
        (tmp_path / 'foo.info').write_text(self.info_data)
        self.reset_objects()
        self.trigger.enable_regen = True
        assert not self.run_trigger('pre_merge', [])
        assert not self.run_trigger('post_merge', [self.dir])

        # verify it doesn't; mtime is fine
        self.reset_objects()
        self.trigger.enable_regen = True
        assert not self.run_trigger('pre_merge', [])
        assert not self.run_trigger('post_merge', [])

        # verify it handles quoting properly, and that it ignores
        # complaints about duplicates.
        self.reset_objects()
        self.trigger.enable_regen = True
        assert not self.run_trigger('pre_merge', [])
        (tmp_path / 'blaidd drwg.info').write_text(self.info_data)
        assert not self.run_trigger('post_merge', [self.dir])

        # verify it passes back failures.
        self.reset_objects()
        self.trigger.enable_regen = True
        assert not self.run_trigger('pre_merge', [])
        (tmp_path / "tiza grande.info").write_text('\n'.join(self.info_data.splitlines()[:-1]))
        l = self.run_trigger('post_merge', [self.dir])
        assert len(l) == 1
        assert 'tiza grande.info' in l[0]

        # verify it holds off on info regen till after unmerge for replaces.
        self.reset_objects(mode=const.REPLACE_MODE)
        assert not self.run_trigger('pre_merge', [])
        assert not self.run_trigger('post_merge', [])
        assert not self.run_trigger('pre_unmerge', [])
        (tmp_path / "tiza grande.info").unlink()
        assert not self.run_trigger('post_unmerge', [self.dir])


class single_attr_change_base:

    kls = triggers.fix_uid_perms
    attr = None

    bad_val = 1

    @staticmethod
    def good_val(val):
        return 2

    def test_metadata(self):
        assert self.kls._engine_types == triggers.INSTALLING_MODES
        assert self.kls.required_csets == ('new_cset', )
        assert self.kls._hooks == ('pre_merge', )

    @property
    def trigger(self):
        return self.kls(1, 2)

    @pytest.mark.parametrize("cset", (
        (),
        (fs.fsFile("/foon", mode=0o644, uid=2, gid=1, strict=False), ),
        (fs.fsFile("/foon", mode=0o646, uid=1, gid=1, strict=False), ),
        (fs.fsFile("/foon", mode=0o4766, uid=1, gid=2, strict=False), ),
        (fs.fsFile("/blarn", mode=0o2700, uid=2, gid=2, strict=False),
         fs.fsDir("/dir", mode=0o500, uid=2, gid=2, strict=False), ),
        (fs.fsFile("/blarn", mode=0o2776, uid=2, gid=2, strict=False),
         fs.fsDir("/dir", mode=0o2777, uid=1, gid=2, strict=False), ),
        (fs.fsFile("/blarn", mode=0o6772, uid=2, gid=2, strict=False),
         fs.fsDir("/dir", mode=0o4774, uid=1, gid=1, strict=False), ),
    ))
    def test_trigger_contents(self, cset):
        new = contentsSet(orig := sorted(cset))
        self.trigger(fake_engine(mode=const.INSTALL_MODE), {'new_cset': new})
        new = sorted(new)
        assert len(orig) == len(new)
        for x, y in zip(orig, new):
            assert orig.__class__ == new.__class__
            for attr in x.__attrs__:
                if self.attr == attr:
                    val = getattr(x, attr)
                    if self.bad_val is not None and val == self.bad_val:
                        assert self.good_val(val) == getattr(y, attr)
                    else:
                        assert self.good_val(val) == getattr(y, attr)
                elif attr != 'chksums':
                    # abuse self as unique singleton.
                    assert getattr(x, attr, self) == getattr(y, attr, self)



class Test_fix_uid_perms(single_attr_change_base):

    kls = triggers.fix_uid_perms
    attr = 'uid'


class Test_fix_gid_perms(single_attr_change_base):

    kls = triggers.fix_gid_perms
    attr = 'gid'


class Test_fix_set_bits(single_attr_change_base):

    kls = triggers.fix_set_bits
    trigger = property(lambda self:self.kls())
    attr = 'mode'

    @staticmethod
    def good_val(val):
        if val & 0o6000 and val & 0o002:
            return val & ~0o6002
        return val


class Test_detect_world_writable(single_attr_change_base):

    kls = triggers.detect_world_writable
    _trigger_override = None

    attr = 'mode'

    @property
    def trigger(self):
        if self._trigger_override is None:
            return self.kls(fix_perms=True)
        return self._trigger_override()

    def good_val(self, val):
        assert self._trigger_override is None, \
            "bug in test code; good_val should not be invoked when a " \
            "trigger override is in place."
        return val & ~0o002

    def test_lazyness(self):
        # ensure it doesn't even look if it won't make noise, and no reporter
        # cset is intentionally *not* a contentset; it'll explode it it tries
        # to access it.
        self.kls().trigger(fake_engine(), None)
        # now verify that the explosion would occur if either settings are on.
        with pytest.raises((AttributeError, TypeError)):
            self.kls().trigger(fake_engine(observer=object()), None)
        with pytest.raises((AttributeError, TypeError)):
            self.kls(fix_perms=True).trigger(fake_engine(), None)

    def test_observer_warn(self):
        warnings = []
        engine = fake_engine(observer=make_fake_reporter(warn=warnings.append))

        self._trigger_override = self.kls()

        def run(fs_objs, fix_perms=False):
            self.kls(fix_perms=fix_perms).trigger(engine,
                contentsSet(fs_objs))

        run([fs.fsFile('/foon', mode=0o770, strict=False)])
        assert not warnings
        run([fs.fsFile('/foon', mode=0o772, strict=False)])
        assert len(warnings) == 1
        assert '/foon' in warnings[0]

        warnings[:] = []

        run([fs.fsFile('/dar', mode=0o776, strict=False),
             fs.fsFile('/bar', mode=0o776, strict=False),
             fs.fsFile('/far', mode=0o770, strict=False)])

        assert len(warnings) == 2
        assert '/dar' in ' '.join(warnings)
        assert '/bar' in ' '.join(warnings)
        assert '/far' not in ' '.join(warnings)


class TestPruneFiles:

    kls = triggers.PruneFiles

    def test_metadata(self):
        assert self.kls.required_csets == ('new_cset', )
        assert self.kls._hooks == ('pre_merge', )
        assert self.kls._engine_types == triggers.INSTALLING_MODES

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

        assert orig == run(lambda s: False)
        assert not run(post_curry(isinstance, fs.fsDir)).dirs()
        assert sorted(orig.files()) == sorted(run(post_curry(isinstance, fs.fsDir)).dirs(True))

        # check noisiness.
        info = []
        engine = fake_engine(observer=make_fake_reporter(info=info.append),
            mode=const.REPLACE_MODE)

        run(lambda s:False)
        assert not info
        run(post_curry(isinstance, fs.fsDir))
        assert len(info) == 2

        # ensure only the relevant files show.
        assert '/cheddar' not in ' '.join(info)
        assert '/sporks-suck' not in ' '.join(info)
        assert '/foons-rule' in ' '.join(info)
        assert '/mango' in ' '.join(info)
