# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import optparse

from twisted.trial import unittest

from pkgcore.util import commandline
from pkgcore.config import errors


def main(config, options, out, err):
    return options


class MainTest(unittest.TestCase):

    def test_weird_parser(self):
        class WeirdParser(commandline.OptionParser):
            def error(self, msg):
                """Ignore errors."""
        self.assertRaises(SystemExit, commandline.main, WeirdParser(), main)

    def test_basics(self):
        self.failUnless(commandline.main(commandline.OptionParser(), main, [],
                                         False))

    def test_debug(self):
        def config_bug_main(config, options, out, err):
            raise errors.InstantiationError('broken')
        self.assertRaises(
            errors.ConfigurationError,
            commandline.main, commandline.OptionParser(), config_bug_main,
            ['--debug'], False)

    def test_empty_sequence(self):
        parser = commandline.OptionParser(option_list=[
                optparse.Option('--seq', action='append')])
        options, values = parser.parse_args([])
        self.assertEqual([], list(options.seq))
