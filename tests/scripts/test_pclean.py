from pkgcore.scripts import pclean
from pkgcore.test.scripts.helpers import ArgParseMixin


class TestCommandline(ArgParseMixin):
    _argparser = pclean.argparser

    suppress_domain = True

    def test_parser(self):
        self.assertError("the following arguments are required: subcommand")
