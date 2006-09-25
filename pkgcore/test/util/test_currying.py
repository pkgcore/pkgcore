# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.util import currying


# Magic to make trial doctest our docstrings.
__doctests__ = [currying]

def passthrough(*args, **kwargs):
    return args, kwargs

# docstring is part of the test

def documented():
    """original docstring"""

class PreCurryTest(TestCase):

    pre_curry = staticmethod(currying.pre_curry)

    def test_pre_curry(self):
        noop = self.pre_curry(passthrough)
        self.assertEquals(noop(), ((), {}))
        self.assertEquals(noop('foo', 'bar'), (('foo', 'bar'), {}))
        self.assertEquals(noop(foo='bar'), ((), {'foo': 'bar'}))
        self.assertEquals(noop('foo', bar='baz'), (('foo',), {'bar': 'baz'}))

        one_arg = self.pre_curry(passthrough, 42)
        self.assertEquals(one_arg(), ((42,), {}))
        self.assertEquals(one_arg('foo', 'bar'), ((42, 'foo', 'bar'), {}))
        self.assertEquals(one_arg(foo='bar'), ((42, ), {'foo': 'bar'}))
        self.assertEquals(
            one_arg('foo', bar='baz'), ((42, 'foo'), {'bar': 'baz'}))

        keyword_arg = self.pre_curry(passthrough, foo=42)
        self.assertEquals(keyword_arg(), ((), {'foo': 42}))
        self.assertEquals(
            keyword_arg('foo', 'bar'), (('foo', 'bar'), {'foo': 42}))
        self.assertEquals(keyword_arg(foo='bar'), ((), {'foo': 'bar'}))
        self.assertEquals(
            keyword_arg('foo', bar='baz'),
            (('foo',), {'bar': 'baz', 'foo': 42}))

        both = self.pre_curry(passthrough, 42, foo=42)
        self.assertEquals(both(), ((42,), {'foo': 42}))
        self.assertEquals(
            both('foo', 'bar'), ((42, 'foo', 'bar'), {'foo': 42}))
        self.assertEquals(both(foo='bar'), ((42, ), {'foo': 'bar'}))
        self.assertEquals(
            both('foo', bar='baz'), ((42, 'foo'), {'bar': 'baz', 'foo': 42}))

    def test_curry_original(self):
        self.assertIdentical(self.pre_curry(passthrough).func, passthrough)

    def test_module_magic(self):
        self.assertIdentical(
            currying.pretty_docs(self.pre_curry(passthrough)).__module__,
            passthrough.__module__)
        # test is kinda useless if they are identical without pretty_docs
        self.assertNotIdentical(
            getattr(self.pre_curry(passthrough), '__module__', None),
            passthrough.__module__)

    def test_pretty_docs(self):
        for func in (passthrough, documented):
            self.assertEquals(
                currying.pretty_docs(
                    self.pre_curry(func), 'new doc').__doc__,
                'new doc')
            self.assertIdentical(
                currying.pretty_docs(self.pre_curry(func)).__doc__,
                func.__doc__)

    def test_instancemethod(self):
        class Test(object):
            method = self.pre_curry(passthrough, 'test')
        test = Test()
        self.assertEquals((('test', test), {}), test.method())


class NativePartialTest(PreCurryTest):

    pre_curry = staticmethod(currying.native_partial)

    def test_instancemethod(self):
        class Test(object):
            method = self.pre_curry(passthrough, 'test')
        test = Test()
        self.assertEquals((('test',), {}), test.method())


class CPyPartialTest(NativePartialTest):

    pre_curry = staticmethod(currying.partial)

    if currying.native_partial is currying.partial:
        skip = 'cpy partial not available.'


class PostCurryTest(TestCase):

    def test_post_curry(self):
        noop = currying.post_curry(passthrough)
        self.assertEquals(noop(), ((), {}))
        self.assertEquals(noop('foo', 'bar'), (('foo', 'bar'), {}))
        self.assertEquals(noop(foo='bar'), ((), {'foo': 'bar'}))
        self.assertEquals(noop('foo', bar='baz'), (('foo',), {'bar': 'baz'}))

        one_arg = currying.post_curry(passthrough, 42)
        self.assertEquals(one_arg(), ((42,), {}))
        self.assertEquals(one_arg('foo', 'bar'), (('foo', 'bar', 42), {}))
        self.assertEquals(one_arg(foo='bar'), ((42, ), {'foo': 'bar'}))
        self.assertEquals(
            one_arg('foo', bar='baz'), (('foo', 42), {'bar': 'baz'}))

        keyword_arg = currying.post_curry(passthrough, foo=42)
        self.assertEquals(keyword_arg(), ((), {'foo': 42}))
        self.assertEquals(
            keyword_arg('foo', 'bar'), (('foo', 'bar'), {'foo': 42}))
        self.assertEquals(
            keyword_arg(foo='bar'), ((), {'foo': 42}))
        self.assertEquals(
            keyword_arg('foo', bar='baz'),
            (('foo',), {'bar': 'baz', 'foo': 42}))

        both = currying.post_curry(passthrough, 42, foo=42)
        self.assertEquals(both(), ((42,), {'foo': 42}))
        self.assertEquals(
            both('foo', 'bar'), (('foo', 'bar', 42), {'foo': 42}))
        self.assertEquals(both(foo='bar'), ((42, ), {'foo': 42}))
        self.assertEquals(
            both('foo', bar='baz'), (('foo', 42), {'bar': 'baz', 'foo': 42}))

    def test_curry_original(self):
        self.assertIdentical(
            currying.post_curry(passthrough).func, passthrough)

    def test_instancemethod(self):
        class Test(object):
            method = currying.post_curry(passthrough, 'test')
        test = Test()
        self.assertEquals(((test, 'test'), {}), test.method())

class TestAliasClassAttr(TestCase):
    def test_alias_class_method(self):
        class kls(object):
            __len__ = lambda s: 3
            lfunc = currying.alias_class_method("__len__")

        c = kls()
        self.assertEqual(c.__len__(), c.lfunc())
        c.__len__ = lambda : 4
        self.assertEqual(c.__len__(), c.lfunc())

