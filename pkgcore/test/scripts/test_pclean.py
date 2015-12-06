# Copyright: 2016 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

from snakeoil import compatibility

from pkgcore.scripts import pclean
from pkgcore.test import TestCase
from pkgcore.test.scripts.helpers import ArgParseMixin


class CommandlineTest(TestCase, ArgParseMixin):

    _argparser = pclean.argparser

    suppress_domain = True

    def test_parser(self):
        if compatibility.is_py3k:
            self.assertError('the following arguments are required: subcommand')
        else:
            self.assertError('too few arguments')
