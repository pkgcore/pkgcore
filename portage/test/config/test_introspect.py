# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from portage.config import introspect


# the docstrings aren't part of the test, but using 'pass' instead
# makes trial's --coverage complain about them.

def args(*args):
    """Function taking a variable number of arguments."""

def kwargs(**kwargs):
    """Function taking keyword arguments."""


def nonopt(one, two):
    """Function taking two non-optional args."""


def alltypes(alist=(), astr='astr', abool=True, aref=object()):
    """Function taking lots of kinds of args."""


class NewStyleClass(object):

    def __init__(self, one, two='two'):
        """Newstyle testclass."""

    def testMember(self, one):
        """Newstyle memberfunc."""

        
class NewStyleClass(object):

    def __init__(self, one, two=object()):
        """Newstyle testclass."""

    def member(self, one):
        """Newstyle memberfunc."""
    

class OldStyleClass:

    def __init__(self, one, two=object()):
        """Newstyle testclass."""

    def member(self, one):
        """Newstyle memberfunc."""


class ConfigTypeFromFunctionTest(unittest.TestCase):

    def test_invalid(self):
        self.assertRaises(TypeError, introspect.configTypeFromCallable, args)
        self.assertRaises(
            TypeError, introspect.configTypeFromCallable, kwargs)

    def test_basic(self):
        nonoptType = introspect.configTypeFromCallable(nonopt)
        self.assertEquals(nonoptType.typename, 'nonopt')
        self.assertEquals(
            nonoptType.types,
            {'one': 'str', 'two': 'str',
             'class': 'callable', 'type': 'str', 'inherit': 'list'})
        self.assertEquals(nonoptType.incrementals, [])
        self.assertEquals(nonoptType.required, ['one', 'two'])
        self.assertEquals(nonoptType.positional, [])
        self.assertEquals(nonoptType.defaults.keys(), [])

    def test_default_types(self):
        testType = introspect.configTypeFromCallable(alltypes)
        self.assertEquals(
            testType.types,
            {'alist': 'list', 'astr': 'str', 'abool': 'bool',
             'aref': 'section_ref',
             'class': 'callable', 'type': 'str', 'inherit': 'list'})
        self.assertEquals(
            sorted(testType.required), ['abool', 'alist', 'aref', 'astr'])
        self.assertEquals(
            sorted(testType.defaults.keys()),
            ['abool', 'alist', 'aref', 'astr'])

    def _test_class_member(self, func):
        testType = introspect.configTypeFromCallable(func)
        self.assertEquals(testType.typename, 'member')
        self.assertEquals(testType.required, ['one'])

    def test_newstyle_instance(self):
        self._test_class_member(NewStyleClass(1).member)

    def test_oldstyle_instance(self):
        self._test_class_member(OldStyleClass(1).member)

    def test_newstyle_class(self):
        self._test_class_member(NewStyleClass.member)

    def test_oldstyle_class(self):
        self._test_class_member(OldStyleClass.member)
        

class ConfigTypeFromClass(unittest.TestCase):

    def _test_basics(self, klass, name):
        testType = introspect.configTypeFromCallable(klass)
        self.assertEquals(testType.typename, name)
        self.assertEquals(sorted(testType.required), ['one', 'two'])
        self.assertEquals(
            testType.defaults.keys(), ['two'])
        self.assertEquals(
            testType.types,
            {'one': 'str', 'two': 'section_ref',
             'class': 'callable', 'type': 'str', 'inherit': 'list'})

    def test_oldstyle(self):
        self._test_basics(OldStyleClass, 'OldStyleClass')

    def test_newstyle(self):
        self._test_basics(NewStyleClass, 'NewStyleClass')
        
