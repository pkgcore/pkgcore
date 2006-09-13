# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from twisted.trial import unittest

from pkgcore.config import introspect


# the docstrings aren't part of the test, but using 'pass' instead
# makes trial's --coverage complain about them.

def argsfunc(*args):
    """Function taking a variable number of arguments."""

def kwargsfunc(**kwargs):
    """Function taking keyword arguments."""


def nonopt(one, two):
    """Function taking two non-optional args."""


def alltypes(alist=(), astr='astr', abool=True, aref=object()):
    """Function taking lots of kinds of args."""


class NewStyleStrClass(object):

    def __init__(self, one, two='two'):
        """Newstyle testclass."""

    def test_member(self, one):
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
        self.assertRaises(TypeError,
                          introspect.config_type_from_callable, argsfunc)
        self.assertRaises(TypeError,
                          introspect.config_type_from_callable, kwargsfunc)

    def test_basic(self):
        nonopt_type = introspect.config_type_from_callable(nonopt)
        self.assertEquals(nonopt_type.typename, 'nonopt')
        self.assertEquals(
            nonopt_type.types,
            {'one': 'str', 'two': 'str',
             'class': 'callable', 'type': 'str', 'inherit': 'list'})
        self.assertEquals(nonopt_type.incrementals, [])
        self.assertEquals(nonopt_type.required, ['one', 'two'])
        self.assertEquals(nonopt_type.positional, ['one', 'two'])
        self.assertEquals(nonopt_type.defaults.keys(), [])

    def test_default_types(self):
        test_type = introspect.config_type_from_callable(alltypes)
        self.assertEquals(
            test_type.types,
            {'alist': 'list', 'astr': 'str', 'abool': 'bool',
             'aref': 'section_ref',
             'class': 'callable', 'type': 'str', 'inherit': 'list'})
        self.assertEquals(
            sorted(test_type.required), ['abool', 'alist', 'aref', 'astr'])
        self.assertEquals(
            sorted(test_type.defaults.keys()),
            ['abool', 'alist', 'aref', 'astr'])

    def _test_class_member(self, func):
        test_type = introspect.config_type_from_callable(func)
        self.assertEquals(test_type.typename, 'member')
        self.assertEquals(test_type.required, ['one'])

    def test_newstyle_instance(self):
        self._test_class_member(NewStyleClass(1).member)

    def test_oldstyle_instance(self):
        self._test_class_member(OldStyleClass(1).member)

    def test_newstyle_class(self):
        self._test_class_member(NewStyleClass.member)

    def test_oldstyle_class(self):
        self._test_class_member(OldStyleClass.member)


class ConfigTypeFromClassTest(unittest.TestCase):

    def _test_basics(self, klass, name, two_override='section_ref'):
        test_type = introspect.config_type_from_callable(klass)
        self.assertEquals(test_type.typename, name)
        self.assertEquals(sorted(test_type.required), ['one', 'two'])
        self.assertEquals(
            test_type.defaults.keys(), ['two'])
        self.assertEquals(
            test_type.types,
            {'one': 'str', 'two': two_override,
             'class': 'callable', 'type': 'str', 'inherit': 'list'})

    def test_oldstyle(self):
        self._test_basics(OldStyleClass, 'OldStyleClass')

    def test_newstyle(self):
        self._test_basics(NewStyleClass, 'NewStyleClass')

    def test_defaults_str(self):
        self._test_basics(NewStyleStrClass, 'NewStyleStrClass',
                          two_override='str')

    def test_config_hint(self):
        class Class(NewStyleClass):
            pkgcore_config_type = introspect.ConfigHint(types={'two':'bool'})
        self._test_basics(Class, 'Class', two_override='bool')
