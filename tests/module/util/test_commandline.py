import argparse
import errno
import io
import os
import pty
import sys
import unittest

import pytest

from pkgcore.config import central, errors
from pkgcore.test.scripts.helpers import ArgParseMixin
from pkgcore.util import commandline

# Careful: the tests should not hit a load_config() call!


def sect():
    """Just a no-op to use as configurable class."""


def mk_config(*args, **kwds):
    return central.CompatConfigManager(
        central.ConfigManager(*args, **kwds))


class _Trigger(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        """Fake a config load."""

        # HACK: force skipping the actual config loading. Might want
        # to do something more complicated here to allow testing if
        # --empty-config actually works.
        namespace.empty_config = True


class TestModifyConfig(ArgParseMixin):

    parser = commandline.ArgumentParser(domain=False, version=False)
    parser.add_argument('--trigger', nargs=0, action=_Trigger)

    def parse(self, *args, **kwargs):
        """Overridden to allow the load_config call."""
        # argparse needs a list (it does make a copy, but it uses [:]
        # to do it, which is a noop on a tuple).
        namespace = self.parser.parse_args(list(args))

        # HACK: force skipping the actual config loading. Might want
        # to do something more complicated here to allow testing if
        # --empty-config actually works.
        namespace.empty_config = True

        return namespace

    def test_empty_config(self):
        assert self.parse('--empty-config', '--trigger')

    def test_modify_config(self):
        namespace = self.parse(
            '--empty-config', '--new-config',
            'foo', 'class', 'module.util.test_commandline.sect',
            '--trigger')
        assert namespace.config.collapse_named_section('foo')

        namespace = self.parse(
            '--empty-config', '--new-config',
            'foo', 'class', 'module.util.test_commandline.missing',
            '--add-config', 'foo', 'class',
            'module.util.test_commandline.sect',
            '--trigger')
        assert namespace.config.collapse_named_section('foo')

        namespace = self.parse(
            '--empty-config',
            '--add-config', 'foo', 'inherit', 'missing',
            '--trigger')
        with pytest.raises(errors.ConfigurationError):
            namespace.config.collapse_named_section('foo')


# This dance is currently necessary because commandline.main wants
# an object it can write text to (to write error messages) and
# pass to PlainTextFormatter, which wants an object it can write
# bytes to. If we pass it a TextIOWrapper then the formatter can
# unwrap it to get at the byte stream (a BytesIO in our case).
def _stream_and_getvalue():
    bio = io.BytesIO()
    f = io.TextIOWrapper(bio, line_buffering=True)

    def getvalue():
        return bio.getvalue().decode('ascii')
    return f, getvalue


class TestMain:

    def assertMain(self, status, outtext, errtext, subcmds, *args, **kwargs):
        out, out_getvalue = _stream_and_getvalue()
        err, err_getvalue = _stream_and_getvalue()
        try:
            commandline.main(subcmds, outfile=out, errfile=err, *args, **kwargs)
        except SystemExit as e:
            assert errtext == err_getvalue()
            assert outtext == out_getvalue()
            assert status == e.args[0], f"expected status {status!r}, got {e.args[0]!r}"
        else:
            self.fail('no exception raised')

    def test_method_run(self):
        argparser = commandline.ArgumentParser(suppress=True)
        argparser.add_argument("--foon")

        @argparser.bind_main_func
        def run(options, out, err):
            out.write(f"args: {options.foon}")
            return 0

        self.assertMain(
            0, 'args: dar\n', '',
            argparser, args=['--foon', 'dar'])

    def test_argparse_with_invalid_args(self):
        argparser = commandline.ArgumentParser(suppress=True, add_help=False)

        @argparser.bind_main_func
        def main(options, out, err):
            pass

        # This is specifically asserting that if given a positional arg (the
        # '1'), which isn't valid in our argparse setup, it returns exit code 2
        # (standard argparse error() exit status).
        self.assertMain(2, '', '', argparser, ['1'])

    # TODO: re-enable once we move to pytest and easier stdout/stderr capture
    # def test_configuration_error(self):
    #     argparser = commandline.ArgumentParser(suppress=True)
    #
    #     @argparser.bind_main_func
    #     def error_main(options, out, err):
    #         raise errors.ConfigurationError('bork')
    #
    #     self.assertMain(
    #         -10, '', 'Error in configuration:\n bork\n', argparser, [])

    def _get_pty_pair(self, encoding='ascii'):
        master_fd, slave_fd = pty.openpty()
        master = os.fdopen(master_fd, 'rb', 0)
        out = os.fdopen(slave_fd, 'wb', 0)
        master = io.TextIOWrapper(master)
        out = io.TextIOWrapper(out)
        return master, out

    @unittest.skipUnless(sys.platform.startswith('linux'), 'test hangs on non-Linux systems')
    def test_tty_detection(self):
        argparser = commandline.ArgumentParser(
            config=False, domain=False, color=True, debug=False,
            quiet=False, verbose=False, version=False)

        @argparser.bind_main_func
        def main(options, out, err):
            for f in (out, err):
                name = f.__class__.__name__
                if name.startswith("native_"):
                    name = name[len("native_"):]
                f.write(name, autoline=False)

        for args, out_kind, err_kind in (
                ([], 'TerminfoFormatter', 'PlainTextFormatter'),
                (['--color=n'], 'PlainTextFormatter', 'PlainTextFormatter'),
                ):
            master, out = self._get_pty_pair()
            err, err_getvalue = _stream_and_getvalue()

            try:
                commandline.main(argparser, args, out, err)
            except SystemExit as e:
                # Important, without this reading the master fd blocks.
                out.close()
                assert None == e.args[0]

                # There can be an xterm title update after this.
                #
                # XXX: Workaround py34 making it harder to read all data from a
                # pty due to issue #21090 (http://bugs.python.org/issue21090).
                out_name = ''
                try:
                    while True:
                        out_name += os.read(master.fileno(), 1).decode()
                except OSError as e:
                    if e.errno == errno.EIO:
                        pass
                    else:
                        raise

                master.close()
                assert out_name.startswith(out_kind) or out_name == 'PlainTextFormatter', \
                    f'expected {out_kind!r}, got {out_name!r}'
                assert err_kind == err_getvalue()
            else:
                self.fail('no exception raised')
