# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import optparse

from pkgcore.test import TestCase

from pkgcore.util import commandline
from pkgcore.config import errors


def main(config, options, out, err):
    return options


# Careful: the commandline.main tests should not hit a load_config() call!

class MainTest(TestCase):

    def test_weird_parser(self):
        class WeirdParser(commandline.OptionParser):
            def error(self, msg):
                """Ignore errors."""
        self.assertRaises(SystemExit, commandline.main, WeirdParser(), main)

    def test_empty_sequence(self):
        parser = commandline.OptionParser(option_list=[
                optparse.Option('--seq', action='append')])
        options, values = parser.parse_args([])
        self.assertEqual([], list(options.seq))
