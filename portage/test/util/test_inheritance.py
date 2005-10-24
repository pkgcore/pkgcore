# Copyright: 2005 Gentoo Foundation
# Author(s): Marien Zwart <m_zwart@123mail.org>
# License: GPL2
# $Id:$


from twisted.trial import unittest

from portage.util import inheritance


class BaseBase(object):
    pass

class BaseOne(BaseBase):
    pass

class BaseTwo(BaseBase):
    pass

class Sub(BaseOne, BaseTwo):
    pass

class Unrelated(object):
    pass


class CheckForBaseTest(unittest.TestCase):

    def test_check_for_base(self):
        self.assertIdentical(
            inheritance.check_for_base(Sub(), [Unrelated, object, BaseTwo]),
            object)
        self.assertIdentical(
            inheritance.check_for_base(Sub(), [Unrelated]), None)
        self.assertIdentical(
            inheritance.check_for_base(Sub(), [BaseTwo]), BaseTwo)
