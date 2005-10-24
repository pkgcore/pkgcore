
from twisted.trial import unittest


from portage.util import strings


class IterTokensTest(unittest.TestCase):

    def test_iter_tokens(self):
        for input, output in [
            ('   foo     bar baz ', ['foo', 'bar', 'baz']),
            ('', []),
            ('  ', []),
            ]:
            self.assertEquals(list(strings.iter_tokens(input)), output)
        for input, splitter, output in [
            ('   foo\tbar\nbaz', '\t\n ', ['foo', 'bar', 'baz']),
            ('fo qof', 'oq', ['f', ' ', 'f']),
            ]:
            self.assertEquals(
                list(strings.iter_tokens(input, splitter)), output)
