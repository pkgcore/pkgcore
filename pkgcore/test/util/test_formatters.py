
import tempfile

from twisted.trial import unittest

from pkgcore.util import formatters


class FormatterTest(unittest.TestCase):

    def _test_stream(self, stream, formatter, *data):
        for inputs, outputs in data:
            stream.seek(0)
            stream.truncate()
            formatter.write(*inputs)
            stream.seek(0)
            self.assertEquals(''.join(outputs), stream.read())

    def test_terminfo(self):
        esc = '\x1b['
        stream = tempfile.TemporaryFile()
        f = formatters.TerminfoFormatter(stream, 'ansi', True)
        f.autoline(False)
        self._test_stream(
            stream, f,
            ((f.bold, 'bold'), (esc, '1m', 'bold', esc, '0;10m')),
            ((f.underline, 'underline'),
             (esc, '4m', 'underline', esc, '0;10m')),
            ((f.fg('red'), 'red'), (esc, '31m', 'red', esc, '39;49m')),
            ((f.fg('red'), 'red', f.bold, 'boldred', f.fg(), 'bold',
              f.reset, 'done'),
             (esc, '31m', 'red', esc, '1m', 'boldred', esc, '39;49m', 'bold',
              esc, '0;10m', 'done')),
            ((42,), ('42',)),
            ((u'\N{SNOWMAN}',), ('?',))
            )
        f.autoline(True)
        self._test_stream(
            stream, f, (('lala',), ('lala', '\n')))

    def test_html(self):
        stream = tempfile.TemporaryFile()
        f = formatters.HTMLFormatter(stream)
        self._test_stream(
            stream, f,
            ((f.bold, 'bold'),
             ('<b>', 'bold', '</b>')),
            ((f.underline, 'underline'),
             ('<ul>', 'underline', '</ul>')),
            ((f.fg('red'), 'red'),
             ('<span style="color: #ff0000">red</span>')),
            ((f.fg('red'), 'red', f.bold, 'boldred',
              f.fg(), 'bold', f.reset, 'done'),
             ('<span style="color: #ff0000">', 'red', '<b>', 'boldred',
              '</b></span><b>', 'bold', '</b>', 'done')),
            ((f.bold, 'bold', f.fg('red'), 'boldred',
              f.reset, 'red',
              f.fg('green'), 'green', f.fg(),
              'done'),
             ('<b>', 'bold', '<span style="color: #ff0000">', 'boldred',
              '</span></b><span style="color: #ff0000">', 'red',
              '<span style="color: #00ff00">', 'green', '</span></span>',
              'done')))
