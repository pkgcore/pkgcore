from pkgcore import plugins
from pkgcore.scripts import pplugincache
from pkgcore.test.scripts.helpers import ArgParseMixin


class TestCommandline(ArgParseMixin):

    _argparser = pplugincache.argparser

    has_config = False

    def test_parser(self):
        assert self.parse().packages == [plugins]
