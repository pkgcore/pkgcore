
import tempfile

from twisted.trial import unittest

from pkgcore.util import formatters


class FormatterTest(unittest.TestCase):

    def _testStream(self, stream, formatter, *data):
        for input, output in data:
            stream.seek(0)
            stream.truncate()
            formatter.write(*input)
            stream.seek(0)
            self.assertEquals(''.join(output), stream.read())

    def test_terminfo(self):
        ESC = '\x1b['
        stream = tempfile.TemporaryFile()
        f = formatters.TerminfoFormatter(stream, 'ansi')
        f.autoline(False)
        self._testStream(
            stream, f,
            ((f.bold, 'bold'), (ESC, '1m', 'bold', ESC, '0;10m')),
            ((f.underline, 'underline'),
             (ESC, '4m', 'underline', ESC, '0;10m')),
            ((f.fg('red'), 'red'), (ESC, '31m', 'red', ESC, '39;49m')),
            ((f.fg('red'), 'red', f.bold, 'boldred', f.fg(), 'bold',
              f.reset, 'done'),
             (ESC, '31m', 'red', ESC, '1m', 'boldred', ESC, '39;49m', 'bold',
              ESC, '0;10m', 'done')),
            ((42,), ('42',)),
            ((u'\N{SNOWMAN}',), ('?',))
            )
        f.autoline(True)
        self._testStream(
            stream, f, (('lala',), ('lala', '\n')))

    def test_html(self):
        stream = tempfile.TemporaryFile()
        f = formatters.HTMLFormatter(stream)
        self._testStream(
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
