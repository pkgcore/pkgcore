# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
file related operations, mainly reading
"""

import re
from shlex import shlex
from mappings import ProtectedDict

def iter_read_bash(bash_source):
	"""
	read file honoring bash commenting rules.  Note that it's considered good behaviour to close filehandles, as such,
	either iterate fully through this, or use read_bash instead.
	once the file object is no longer referenced, the handle will be closed, but be proactive instead of relying on the
	garbage collector.
	
	@param bash_source: either a file to read from, or a string holding the filename to open
	"""
	if isinstance(bash_source, basestring):
		bash_source = open(bash_source, 'r', 32384)
	for s in bash_source:
		s = s.strip()
		if s.startswith("#") or s == "":
			continue
		yield s
	bash_source.close()


def read_bash(bash_source):
	return list(iter_read_bash(bash_source))
read_bash.__doc__ = iter_read_bash.__doc__


def read_dict(bash_source, splitter="=", ignore_malformed=False, source_isiter=False):
	"""
	read key value pairs, splitting on specified splitter, using iter_read_bash for filtering comments
	
	@param bash_source: either a file to read from, or a string holding the filename to open

	"""
	d = {}
	if not source_isiter:
		i = iter_read_bash(bash_source)
	else:
		i = bash_source
	line_count = 1
	try:
		for k in i:
			line_count += 1
			try:
				k, v = k.split(splitter, 1)
			except ValueError:
				if not ignore_malformed:
					raise ParseError(file, line_count)
			else:
				if len(v) > 2 and v[0] == v[-1] and v[0] in ("'", '"'):
					v = v[1:-1]
				d[k] = v
	finally:
		del i
	return d

def read_bash_dict(bash_source, vars_dict=None, ignore_malformed=False, sourcing_command=None):
	"""
	read bash source, yielding a dict of vars

	@param bash_source: either a file to read from, or a string holding the filename to open
	@param vars_dict: initial 'env' for the sourcing, and is protected from modification.
	@type vars_dict: dict or None
	@param sourcing_command: controls whether a source command exists, if one does and is encountered, then this func
	@type sourcing_command: callable
	@param ignore_malformed: if malformed syntax, whether to ignore that line or throw a ParseError
	@raise ParseError: thrown if ignore_malformed is False, and invalid syntax is encountered
	@return: dict representing the resultant env if bash executed the source
	"""

	# quite possibly I'm missing something here, but the original portage_util getconfig/varexpand seemed like it
	# only went halfway.  The shlex posix mode *should* cover everything.

	if vars_dict is not None:
		d, protected = ProtectedDict(vars_dict), True
	else:
		d, protected = {}, False
	f = open(bash_source, 'r', 32384)
	s = bash_parser(f, sourcing_command=sourcing_command, env=d)

	try:
		tok = ""
		try:
			while tok is not None:
				key = s.get_token()
				if key is None:
					break
				eq, val = s.get_token(), s.get_token()
				if eq != '=' or val is None:
					if not ignore_malformed:
						raise ParseError(bash_source, s.lineno)
					else:
						break
				d[key] = val
		except ValueError:
			raise ParseError(bash_source, s.lineno)
	finally:
		f.close()
	if protected:
		d = d.new
	return d


var_find = re.compile(r'\\?(\${\w+}|\$\w+)')
backslash_find = re.compile(r'\\.')
def nuke_backslash(s):
	s = s.group()
	if s == "\\\n":
		return "\n"
	try:
		return chr(ord(s))
	except TypeError:
		return s[1]

class bash_parser(shlex):
	def __init__(self, source, sourcing_command=None, env=None):
		shlex.__init__(self, source, posix=True)
		self.wordchars += "${}/.-+/:"
		if sourcing_command is not None:
			self.source = sourcing_command
		if env is None:
			env = {}
		self.env = env
		self.__pos = 0

	def __setattr__(self, attr, val):
		if attr == "state" and "state" in self.__dict__:
			if (self.state, val) in (('"', 'a'), ('a', '"'), ('a', ' '), ("'", 'a')):
				strl = len(self.token)
				if self.__pos != strl:
					self.changed_state.append((self.state, self.token[self.__pos:]))
				self.__pos = strl
		self.__dict__[attr] = val

	def sourcehook(self, newfile):
		try:
			return shlex.sourcehook(self, newfile)
		except IOError, ie:
			raise ParseError(newfile, 0, str(ie))

	def read_token(self):
		self.changed_state = []
		self.__pos = 0
		tok = shlex.read_token(self)
		if tok is None:
			return tok
		self.changed_state.append((self.state, self.token[self.__pos:]))
		tok = ''
		for s, t in self.changed_state:
			if s in ('"', "a"):
				tok += self.var_expand(t)
			else:
				tok += t
		return tok

	def var_expand(self, val):
		prev, pos = 0, 0
		l = []
		match = var_find.search(val)
		while match is not None:
			pos = match.start()
			if val[pos] == '\\':
				# it's escaped.	 either it's \\$ or \\${ , either way, skipping two ahead handles it.
				pos += 2
			else:
				var = val[match.start():match.end()].strip("${}")
				if prev != pos:
					l.append(val[prev:pos])
				if var in self.env:
					l.append(self.env[var])
				else:
					l.append("")
				prev = pos = match.end()
			match = var_find.search(val, pos)

		# do \\ cleansing, collapsing val down also.
		val = backslash_find.sub(nuke_backslash, ''.join(l) + val[prev:])
		return val


class ParseError(Exception):

	def __init__(self, file, line, errmsg=None):
		self.file, self.line, self.errmsg = file, line, errmsg

	def __str__(self):
		if self.errmsg is not None:
			return "error parsing '%s' on or before %i: err %s" % (self.file, self.line, self.errmsg)
		return "error parsing '%s' on or before %i" % (self.file, self.line)
