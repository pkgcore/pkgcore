# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$


import tempfile
from StringIO import StringIO

from twisted.trial import unittest

# ick, a module shadowing a builtin. import its contents instead.
from portage.util.file import iter_read_bash, read_bash, read_dict
from portage.util.file import read_bash_dict, ParseError


class TestBashCommentStripping(unittest.TestCase):

	def test_iter_read_bash(self):
		self.assertEquals(
			list(iter_read_bash(StringIO(
						'\n'
						'# hi I am a comment\n'
						'I am not\n'))),
			['I am not'])

	def test_read_bash(self):
		self.assertEquals(
			read_bash(StringIO(
					'\n'
					'# hi I am a comment\n'
					'I am not\n')),
			['I am not'])


class TestReadBashConfig(unittest.TestCase):
	
	def test_read_dict(self):
		self.assertEquals(
			read_dict(StringIO(
					'\n'
					'# hi I am a comment\n'
					'foo1=bar\n'
					'foo2="bar"\n'
					'foo3=\'bar"\n'
					)),
			{'foo1': 'bar',
			 'foo2': 'bar',
			 'foo3': '\'bar"',
			 })
		self.assertEquals(
			read_dict(['foo=bar'], source_isiter=True), {'foo': 'bar'})
		self.assertRaises(
			ParseError, read_dict, ['invalid'], source_isiter=True)
		self.assertEquals(
			read_dict(
				['invalid', 'foo=bar', '# blah'], source_isiter=True,
				ignore_malformed=True),
			{'foo': 'bar'})


class ReadBashDictTest(unittest.TestCase):

	def setUp(self):
		self.validFile = tempfile.NamedTemporaryFile()
		self.validFile.write(
			'# hi I am a comment\n'
			'foo1=bar\n'
			"foo2='bar'\n"
			'foo3="bar"\n')
		self.validFile.flush()
		self.invalidFile = tempfile.NamedTemporaryFile()
		self.invalidFile.write(
			'# hi I am a comment\n'
			'foo1=bar\n'
			"foo2='bar'foo3=\"bar\"")
		self.invalidFile.flush()
		self.sourcingFile = tempfile.NamedTemporaryFile()
		self.sourcingFile.write('source "%s"\n' % self.validFile.name)
		self.sourcingFile.flush()

	def tearDown(self):
		del self.validFile
		del self.invalidFile
		del self.sourcingFile
	
	def test_read_bash_dict(self):
		# TODO this is not even close to complete
		self.assertEquals(
			read_bash_dict(self.validFile.name),
			{'foo1': 'bar', 'foo2': 'bar', 'foo3': 'bar'})
		self.assertRaises(ParseError, read_bash_dict, self.invalidFile.name)
		self.assertEquals(
			read_bash_dict(self.invalidFile.name, ignore_malformed=True),
			{'foo1': 'bar', 'foo2': 'barfoo3'})

	def test_sourcing(self):
		# TODO this is not even close to complete
		self.assertEquals(
            read_bash_dict(self.sourcingFile.name, sourcing_command='source'),
            {'foo1': 'bar', 'foo2': 'bar', 'foo3': 'bar'})
			
