# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.util import caching

def gen_test(WeakInstMeta):
    class weak_slotted(object):
        __metaclass__ = WeakInstMeta
        __inst_caching__ = True
        __slots__ = ('one',)

    class weak_inst(object):
        __metaclass__ = WeakInstMeta
        __inst_caching__ = True
        counter = 0
        def __new__(cls, *args, **kwargs):
            cls.counter += 1
            return object.__new__(cls)
        def __init__(self, *args, **kwargs):
            pass
        @classmethod
        def reset(cls):
            cls.counter = 0

    class automatic_disabled_weak_inst(weak_inst):
        pass

    class explicit_disabled_weak_inst(weak_inst):
        __inst_caching__ = False

    class reenabled_weak_inst(automatic_disabled_weak_inst):
        __inst_caching__ = True

    class TestWeakInstMeta(TestCase):

        def test_reuse(self, kls=weak_inst):
            kls.reset()
            o = kls()
            self.assertIdentical(o, kls())
            self.assertEqual(kls.counter, 1)
            del o
            kls()
            self.assertEqual(kls.counter, 2)

        def test_disabling_inst(self):
            weak_inst.reset()
            for x in (1, 2):
                o = weak_inst(disable_inst_caching=True)
                self.assertIdentical(weak_inst.counter, x)
            del o
            o = weak_inst()
            self.assertFalse(o is weak_inst(disable_inst_caching=True))

        def test_class_disabling(self):
            automatic_disabled_weak_inst.reset()
            self.assertNotIdentical(
                automatic_disabled_weak_inst(), automatic_disabled_weak_inst())
            self.assertNotIdentical(
                explicit_disabled_weak_inst(), explicit_disabled_weak_inst())

        def test_reenabled(self):
            self.test_reuse(reenabled_weak_inst)

        # Read this before doing anything with the warnings-related
        # tests unless you really enjoy debugging Heisenbugs.
        #
        # The warnings module is optimized for the common case of
        # warnings that should be ignored: it stores a "key"
        # consisting of the type of warning, the warning message and
        # the module it originates from in a dict (cleverly hidden
        # away in the globals() of the frame calling warn()) if a
        # warning should be ignored, and then immediately ignores
        # warnings matching that key, *without* looking at the current
        # filters list.
        #
        # This means that if our test(s) with warnings ignored run
        # before tests with warnings turned into exceptions (test
        # order is random, enter Heisenbugs) and both tests involve
        # the same exception message they will screw up the tests.
        #
        # To make matters more interesting the warning message we deal
        # with here is not constant. Specifically it contains the
        # repr() of an argument tuple, containing a class instance,
        # which means the message will contain the address that object
        # is stored at!
        #
        # This exposed itself as crazy test failures where running
        # from .py fails and from .pyc works (perhaps related to the
        # warnings module taking a different codepath for this) and
        # creating objects or setting pdb breakpoints before that
        # failure caused the test to pass again.
        #
        # What all this means: Be 100% positively absolutely sure
        # test_uncachable and test_uncachable_warnings do not see the
        # same warning message ever. We do that by making sure their
        # warning messages contain a different classname
        # (RaisingHashFor...).

        def test_uncachable(self):
            weak_inst.reset()

            # This name is *important*, see above.
            class RaisingHashForTestUncachable(object):
                def __init__(self, error):
                    self.error = error
                def __hash__(self):
                    raise self.error

            self.assertTrue(weak_inst([]) is not weak_inst([]))
            self.assertEqual(weak_inst.counter, 2)
            for x in (TypeError, NotImplementedError):
                self.assertNotIdentical(
                    weak_inst(RaisingHashForTestUncachable(x)),
                    weak_inst(RaisingHashForTestUncachable(x)))

        # These are applied in reverse order. Effect is UserWarning is
        # ignored and everything else is an error.
        test_uncachable.suppress = [
            (('error',), {}), (('ignore',), {'category': UserWarning})]

        def test_force_caching(self):
            class weak_forced(object):
                __metaclass__ = WeakInstMeta
                __force_caching__ = True
                __init__ = lambda s, *a, **kw:None

                def __new__(cls, *args, **kwds):
                    return object.__new__(cls)
            
            # This name is *important*, see above.
            class RaisingHashForTestForced(object):
                def __init__(self, error):
                    self.error = error
                def __hash__(self):
                    raise self.error

            self.assertRaises(TypeError, weak_forced, [])
            self.assertRaises(TypeError, weak_forced, None,
                disable_inst_caching=True)

        # These are applied in reverse order. Effect is UserWarning is
        # ignored and everything else is an error.
        test_force_caching.suppress = [
            (('error',), {}), (('ignore',), {'category': UserWarning})]

        def test_uncachable_warning(self):
            # This name is *important*, see above.
            class RaisingHashForTestUncachableWarnings(object):
                def __init__(self, error):
                    self.error = error
                def __hash__(self):
                    raise self.error

            for x in (TypeError, NotImplementedError):
                self.assertRaises(UserWarning, weak_inst,
                                  RaisingHashForTestUncachableWarnings(x))

        test_uncachable_warning.suppress = [
            (('error',), {'category': UserWarning})]

        def test_hash_collision(self):
            class BrokenHash(object):
                def __hash__(self):
                    return 1
            self.assertNotIdentical(weak_inst(BrokenHash()),
                                weak_inst(BrokenHash()))

        def test_weak_slot(self):
            weak_slotted()

        def test_keyword_args(self):
            o = weak_inst(argument=1)
            self.assertIdentical(o, weak_inst(argument=1))
            self.assertNotIdentical(o, weak_inst(argument=2))

    # Hack to make it show up with a different name in trial's output
    TestWeakInstMeta.__name__ = WeakInstMeta.__name__ + 'Test'

    return TestWeakInstMeta

# "Invalid name"
# pylint: disable-msg=C0103

native_WeakInstMetaTest = gen_test(caching.native_WeakInstMeta)

if caching.cpy_WeakInstMeta is not None:
    cpy_WeakInstMetaTest = gen_test(caching.cpy_WeakInstMeta)
else:
    # generate fake test and mark it as skip
    cpy_WeakInstMetaTest = gen_test(type)
    cpy_WeakInstMetaTest.skip = "cpython cpv extension isn't available"

