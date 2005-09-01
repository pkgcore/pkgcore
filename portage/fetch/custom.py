# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

import os
import base
from portage.spawn import spawn_bash, userpriv_capable
from portage.chksum import get_handler
from fetchable import fetchable
import errors
from portage.os_data import portage_uid, portage_gid
from portage.util.fs import ensure_dirs

class MalformedCommand(errors.base):
	def __init__(self, command):	self.command = command
	def __str__(self):	return "fetchcommand is malformed: "+self.command

class fetcher(base.fetcher):
	def __init__(self, distdir, command, required_chksums=[], userpriv=True, attempts=10, readonly=False, **conf):
		self.distdir = distdir
		required_chksums = map(lambda x: x.lower(), required_chksums)
		if len(required_chksums) == 1 and required_chksums[0] == "all":
			self.required_chksums = None
		else:
			self.required_chksums = required_chksums
		new_command = command.replace("${DISTDIR}", self.distdir)
		new_command = new_command.replace("$DISTDIR", self.distdir)
		new_command = new_command.replace("${URI}", "%(URI)s")
		new_command = new_command.replace("$URI", "%(URI)s")
		if new_command == command:
			raise MalformedCommand(command)
		self.command = new_command
		self.attempts = attempts
		self.userpriv = userpriv
		kw = {"mode":0775}
		if readonly:
			kw["mode"] = 0555
		if userpriv:
			kw["uid"] = portage_uid
			kw["gid"] = portage_gid
		if not ensure_dirs(self.distdir, **kw):
			raise errors.distdirPerms(self.distdir, "if userpriv, uid must be %i, gid must be %i.  if not readonly, directory must be 0775, else 0555")
		
			
	def fetch(self, target):
		if not isinstance(target, fetchable):
			raise TypeError("target must be fetchable instance/derivative: %s" % target)

		fp = os.path.join(self.distdir, target.filename)
		
		uri = iter(target.uri)
		if self.userpriv and userpriv_capable:
			extra = {"uid":portage_uid, "gid":portage_gid}
		else:
			extra = {}
		attempts = self.attempts
		try:
			while attempts >= 0:
				c = self._verify(fp, target)
				if c == 0:
					return fp
				elif c > 0:
					try:
						os.unlink(fp)
					except OSError, oe:
						raise errors.UnmodifiableFile(fp, oe)

				# yeah, it's funky, but it works.
				if attempts > 0:
					u = uri.next()
					# note we're not even checking the results. the verify portion of the loop handles this.
					# iow, don't trust their exit code.  trust our chksums instead.
					spawn_bash(self.command % {"URI":u}, **extra)
					
				attempts -= 1
		except StopIteration:
			return None

		return None

