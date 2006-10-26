# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import optparse

from pkgcore.test import TestCase

from pkgcore.util import commandline
from pkgcore.config import basics, central


# Careful: the tests should not hit a load_config() call!


class OptionsTest(TestCase):

    def test_empty_sequence(self):
        parser = commandline.OptionParser(option_list=[
                optparse.Option('--seq', action='append')])
        options, values = parser.parse_args([])
        self.assertEqual([], list(options.seq))

    def test_debug(self):
        # Hack: we can modify this from inside the callback.
        confdict = {}
        def callback(option, opt_str, value, parser):
            section = parser.values.config.collapse_named_section('sect')
            # It would actually be better if debug was True here.
            # We check for an unintended change, not ideal behaviour.
            self.assertFalse(section.debug)
            confdict['sect'] = section

        def sect():
            """Just a no-op to use as configurable class."""

        parser = commandline.OptionParser(option_list=[
                optparse.Option('-a', action='callback', callback=callback)])
        values = parser.get_default_values()
        values._config = central.ConfigManager([{
                    'sect': basics.HardCodedConfigSection({'class': sect})}])

        values, args = parser.parse_args(['-a', '--debug'], values)
        self.assertFalse(args)
        self.assertTrue(values.debug)
        self.assertTrue(confdict['sect'].debug)

        values = parser.get_default_values()
        values._config = central.ConfigManager([{
                    'sect': basics.HardCodedConfigSection({'class': sect})}])
        values, args = parser.parse_args(['-a'], values)
        self.assertFalse(args)
        self.assertFalse(values.debug)
        self.assertFalse(confdict['sect'].debug)


def main(options, out, err):
    return options

class MainTest(TestCase):

    def test_weird_parser(self):
        class WeirdParser(commandline.OptionParser):
            def error(self, msg):
                """Ignore errors."""
        self.assertEquals(
            1, commandline.main(WeirdParser(), main, ['1'], False))
