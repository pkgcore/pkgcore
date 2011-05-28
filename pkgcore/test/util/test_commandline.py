# Copyright: 2006-2007 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


import os
import gc
import pty
import StringIO
import optparse
import weakref

from snakeoil import compatibility
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

    def test_arguments_allowed(self):

        class myparser(commandline.OptionParser):
            pass

        self.assertRaises(helpers.Error, myparser().parse_args, ["asdf"])

        class myparser(commandline.OptionParser):
            arguments_allowed = True
        values, args = myparser().parse_args(["asdf"])
        self.assertFalse(args)
        self.assertEqual(list(values.arguments), ["asdf"])


    def test_copy_protections(self):

        class myparser(commandline.OptionParser):
            pass

        inst = myparser()
        self.assertNotIdentical(myparser.standard_option_list, inst.standard_option_list)
        self.assertEqual(len(myparser.standard_option_list),
            len(inst.standard_option_list))

        # verify that we didn't typo above...
        self.assertTrue(myparser.standard_option_list)

        for kls_item, inst_item in zip(myparser.standard_option_list, inst.standard_option_list):
            self.assertNotIdentical(kls_item, inst_item)
            self.assertFalse(hasattr(kls_item, 'container'))
            # just verify our assumptions; if this fails, then we can't
            # trust the tests above since optparse has changed behaviour.
            self.assertTrue(hasattr(inst_item, 'container'))

    def test_optparse_parser_leak(self):
        # This makes sure there is no global reference to the parser.
        # That is not usually critical, but an extra safety net in case
        # the parser (incorrectly) keeps important references around.
        # (at some point it kept the values object alive).
        # This test would fail if standard_option_list was used.
        parser = commandline.OptionParser()
        values, args = parser.parse_args([])
        parserref = weakref.ref(parser)
        del parser
        # XXX I think this is a bug: the values object has a strong
        # ref to the parser via _raise_error...
        del values
        # This is necessary because the parser and its options have
        # cyclical references to each other.
        gc.collect()
        self.assertIdentical(None, parserref())

    def test_optparse_values_leak(self):
        # This makes sure nothing keeps a reference to the optparse
        # "values" object. This is somewhat important because that
        # "values" object has a reference to the config central
        # object, which keeps a ton of things alive.
        parser = commandline.OptionParser()
        values, args = parser.parse_args([])
        valuesref = weakref.ref(values)
        del values
        self.assertIdentical(None, valuesref())

    def test_bool_type(self):
        parser = helpers.mangle_parser(commandline.OptionParser())
        parser.add_option("--testing", action='store', type='bool',
            default=None)

        for raw_val in ("n", "no", "false"):
            for allowed in (raw_val.upper(), raw_val.lower()):
                values, args = parser.parse_args(['--testing=' + allowed])
                self.assertEqual(values.testing, False,
                    msg="for --testing=%s, got %r, expected False" %
                        (allowed, values.testing))

        for raw_val in ("y", "yes", "true"):
            for allowed in (raw_val.upper(), raw_val.lower()):
                values, args = parser.parse_args(['--testing=' + allowed])
                self.assertEqual(values.testing, True,
                    msg="for --testing=%s, got %r, expected False" %
                        (allowed, values.testing))

        try:
            parser.parse_args(["--testing=invalid"])
        except helpers.Error, e:
            pass
        else:
            self.fail("no error message thrown for --testing=invalid")


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

    def test_method_run(self):
        class newparser(commandline.OptionParser):
            def __init__(self, *args, **kwds):
                commandline.OptionParser.__init__(self, *args, **kwds)
                self.add_option("--foon", action='store',)

            def run(self, options, out, err):
                out.write("args: %s" % (options.foon,))
                return 0

        self.assertMain(
            0, 'args: dar\n', '',
            {None:newparser}, args=['--foon', 'dar'])

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

    def _get_pty_pair(self, encoding='ascii'):
        master_fd, slave_fd = pty.openpty()
        master = os.fdopen(master_fd, 'rb', 0)
        out = os.fdopen(slave_fd, 'wb', 0)
        if compatibility.is_py3k:
            # note that 2to3 converts the global StringIO import to io
            master = io.TextIOWrapper(master)
            out = io.TextIOWrapper(out)
        return master, out


    def test_tty_detection(self):
        def main(options, out, err):
            for f in (out, err):
                name = f.__class__.__name__
                if name.startswith("native_"):
                    name = name[len("native_"):]
                f.write(name, autoline=False)

        for args, out_kind, err_kind in [
            ([], 'TerminfoFormatter', 'PlainTextFormatter'),
            (['--nocolor'], 'PlainTextFormatter', 'PlainTextFormatter'),
            ]:
            master, out = self._get_pty_pair()
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
                self.assertTrue(
                    out_name.startswith(out_kind) or out_name == 'PlainTextFormatter',
                    'expected %r, got %r' % (out_kind, out_name))
                self.assertEqual(err_kind, err.getvalue())
            else:
                self.fail('no exception raised')
