# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase, mixins
from pkgcore.merge import triggers
from pkgcore.util.currying import partial

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
