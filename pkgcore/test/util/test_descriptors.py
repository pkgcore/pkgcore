# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import TestCase

from pkgcore.util import descriptors


class ClassProp(object):

    @descriptors.classproperty
    def test(cls):
        """Just an example."""
        return 'good', cls


class DescriptorTest(TestCase):

    def test_classproperty(self):
        self.assertEquals(('good', ClassProp), ClassProp.test)
        self.assertEquals(('good', ClassProp), ClassProp().test)
