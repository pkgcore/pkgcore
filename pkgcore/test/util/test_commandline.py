# Copyright: 2006-2007 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import os
import pty
import StringIO
import optparse

from pkgcore.test import TestCase
from pkgcore.test.scripts import helpers

from pkgcore.util import commandline
from pkgcore.config import basics, central, configurable, errors


# Careful: the tests should not hit a load_config() call!

def sect():
    """Just a no-op to use as configurable class."""


class OptionsTest(TestCase):

    def test_empty_sequence(self):
        parser = helpers.mangle_parser(commandline.OptionParser(option_list=[
                    optparse.Option('--seq', action='append')]))
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

        parser = commandline.OptionParser(option_list=[
                optparse.Option('-a', action='callback', callback=callback)])
        parser = helpers.mangle_parser(parser)
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

    def test_config_callback(self):
        @configurable(typename='foon')
        def test():
            return 'foon!'
        parser = helpers.mangle_parser(commandline.OptionParser())
        parser.add_option('--spork', action='callback',
                          callback=commandline.config_callback,
                          type='string', callback_args=('foon',))
        parser.add_option('--foon', action='callback',
                          callback=commandline.config_callback,
                          type='string', callback_args=('foon', 'utensil'))
        values = parser.get_default_values()
        values._config = central.ConfigManager([{
                    'afoon': basics.HardCodedConfigSection({'class': test})}])

        values, args = parser.parse_args(['--spork', 'afoon'], values)
        self.assertEqual('foon!', values.spork)

        try:
            parser.parse_args(['--spork', 'nofoon'], values)
        except helpers.Error, e:
            self.assertEqual(
                "'nofoon' is not a valid foon for --spork "
                "(valid values: 'afoon')",
                str(e))
        else:
            self.fail('no exception raised')

        try:
            parser.parse_args(['--foon', 'nofoon'], values)
        except helpers.Error, e:
            self.assertEqual(
                "'nofoon' is not a valid utensil for --foon "
                "(valid values: 'afoon')",
                str(e))
        else:
            self.fail('no exception raised')


class ModifyParser(commandline.OptionParser):

    def _trigger(self, option, opt_str, value, parser):
        """Fake a config load."""
        # HACK: force skipping the actual config loading. Might want
        # to do something more complicated here to allow testing if
        # --empty-config actually works.
        parser.values.empty_config = True
        parser.values.config

    def __init__(self):
        commandline.OptionParser.__init__(self)
        self.add_option('--trigger', action='callback', callback=self._trigger)


class ModifyConfigTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(ModifyParser())

    def parse(self, *args, **kwargs):
        """Overridden to allow the load_config call."""
        values = self.parser.get_default_values()
        # optparse needs a list (it does make a copy, but it uses [:]
        # to do it, which is a noop on a tuple).
        options, args = self.parser.parse_args(list(args), values)
        self.assertFalse(args)
        return options

    def test_empty_config(self):
        self.assertError(
            'Configuration already loaded. If moving the option earlier on '
            'the commandline does not fix this report it as a bug.',
            '--trigger', '--empty-config')
        self.assertTrue(self.parse('--empty-config', '--trigger'))

    def test_modify_config(self):
        self.assertError(
            'Configuration already loaded. If moving the option earlier on '
            'the commandline does not fix this report it as a bug.',
            '--empty-config', '--trigger',
            '--new-config','foo', 'class', 'sect')
        values = self.parse(
            '--empty-config', '--new-config',
            'foo', 'class', 'pkgcore.test.util.test_commandline.sect',
            '--trigger')
        self.assertTrue(values.config.collapse_named_section('foo'))
        values = self.parse(
            '--empty-config', '--new-config',
            'foo', 'class', 'pkgcore.test.util.test_commandline.missing',
            '--add-config', 'foo', 'class',
            'pkgcore.test.util.test_commandline.sect',
            '--trigger')
        self.assertTrue(values.config.collapse_named_section('foo'))
        self.assertError(
            "'class' is already set (to 'first')",
            '--empty-config',
            '--new-config', 'foo', 'class', 'first',
            '--new-config', 'foo', 'class', 'foon',
            '--trigger')
        values = self.parse(
            '--empty-config',
            '--add-config', 'foo', 'inherit', 'missing',
            '--trigger')
        self.assertRaises(
            errors.ConfigurationError,
            values.config.collapse_named_section, 'foo')


def main(options, out, err):
    return options


class MainTest(TestCase):

    def assertMain(self, status, outtext, errtext, *args, **kwargs):
        out = StringIO.StringIO()
        err = StringIO.StringIO()
        try:
            commandline.main(outfile=out, errfile=err, *args, **kwargs)
        except commandline.MySystemExit, e:
            self.assertEqual(status, e.args[0])
            self.assertEqual(outtext, out.getvalue())
            self.assertEqual(errtext, err.getvalue())
        else:
            self.fail('no exception raised')

    def test_weird_parser(self):
        class WeirdParser(commandline.OptionParser):
            def error(self, msg):
                """Ignore errors."""
        self.assertMain(
            1, '', '',
            {None: (WeirdParser, main)}, ['1'])

    def test_subcommand_list(self):
        def main_one(options, out, err):
            """Sub one!"""
        def main_two(options, out, err):
            """Subcommand two, with a longer name and docstring."""
        def main_three(options, out, err):
            pass # Intentionally undocumented.

        self.assertMain(
            1, '', '''\
Usage: spork <command>

Commands:
  one          Sub one!
  three
  twoandahalf  Subcommand two, with a longer name and docstring.

Use --help after a subcommand for more help.
''', {
                'one': (commandline.OptionParser, main_one),
                'twoandahalf': (commandline.OptionParser, main_two),
                'three': (commandline.OptionParser, main_three),
                }, [], script_name='spork')

    def test_subcommand(self):
        class SubParser(commandline.OptionParser):
            def check_values(self, values, args):
                values, args = commandline.OptionParser.check_values(
                    self, values, args)
                values.args = args
                values.progname = self.prog
                return values, ()
        def submain(options, out, err):
            self.assertEqual(options.args, ['subarg'])
            self.assertEqual(options.progname, 'fo sub')

        self.assertMain(
            None, '', '',
            {'sub': (SubParser, submain)}, ['sub', 'subarg'], script_name='fo')

    def test_configuration_error(self):
        def error_main(options, out, err):
            raise errors.ConfigurationError('bork')
        class NoLoadParser(commandline.OptionParser):
            """HACK: avoid the config load --debug triggers."""
            def get_default_values(self):
                values = commandline.OptionParser.get_default_values(self)
                values._config = central.ConfigManager()
                return values
        self.assertMain(
            1, '', 'Error in configuration:\nbork\n',
            {None: (NoLoadParser, error_main)}, [])
        self.assertRaises(
            errors.ConfigurationError, self.assertMain,
            1, '', '',
            {None: (NoLoadParser, error_main)}, ['--debug'])

    def test_tty_detection(self):
        def main(options, out, err):
            for f in (out, err):
                f.write(f.__class__.__name__, autoline=False)

        for args, out_kind, err_kind in [
            ([], 'TerminfoFormatter', 'PlainTextFormatter'),
            (['--nocolor'], 'PlainTextFormatter', 'PlainTextFormatter'),
            ]:
            master_fd, slave_fd = pty.openpty()
            out = os.fdopen(slave_fd, 'a', 0)
            master = os.fdopen(master_fd, 'r', 0)
            err = StringIO.StringIO()

            try:
                commandline.main(
                    {None: (commandline.OptionParser, main)}, args, out, err)
            except commandline.MySystemExit, e:
                # Important, without this master.read() blocks.
                out.close()
                self.assertEqual(None, e.args[0])
                # There can be an xterm title update after this.
                out_name = master.read()
                self.failUnless(
                    out_name.startswith(out_kind),
                    'expected %r, got %r' % (out_kind, out_name))
                self.assertEqual(err_kind, err.getvalue())
            else:
                self.fail('no exception raised')
