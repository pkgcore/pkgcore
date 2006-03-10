# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: fs_template.py 2270 2005-11-10 00:17:33Z ferringb $

import os
import template, cache_errors
from portage.os_data import portage_gid
from portage.fs.util import ensure_dirs

class FsBased(template.database):
	"""template wrapping fs needed options, and providing _ensure_access as a way to 
	attempt to ensure files have the specified owners/perms"""

	def __init__(self, *args, **config):
		"""throws InitializationError if needs args aren't specified
		gid and perms aren't listed do to an oddity python currying mechanism
		gid=portage_gid
		perms=0665"""

		for x,y in (("gid",portage_gid),("perms",0664)):
			if x in config:
				setattr(self, "_"+x, config[x])
				del config[x]
			else:
				setattr(self, "_"+x, y)
		super(FsBased, self).__init__(*args, **config)

		if self.label.startswith(os.path.sep):
			# normpath.
			self.label = os.path.sep + os.path.normpath(self.label).lstrip(os.path.sep)


	def _ensure_access(self, path, mtime=-1):
		"""returns true or false if it's able to ensure that path is properly chmod'd and chowned.
		if mtime is specified, attempts to ensure that's correct also"""
		try:
			os.chown(path, -1, self._gid)
			os.chmod(path, self._perms)
			if mtime:
				mtime=long(mtime)
				os.utime(path, (mtime, mtime))
		except OSError, IOError:
			return False
		return True

	def _ensure_dirs(self, path=None):
		"""if path != None, ensures self.location + '/' + path, else self.location"""
		if path != None:
			path = self.location + os.path.sep + os.path.dirname(path)
		else:
			path = self.location
		return ensure_dirs(path)
	
def gen_label(base, label):
	"""if supplied label is a path, generate a unique label based upon label, and supplied base path"""
	if label.find(os.path.sep) == -1:
		return label
	label = label.strip("\"").strip("'")
	label = os.path.join(*(label.rstrip(os.path.sep).split(os.path.sep)))
	tail = os.path.split(label)[1]
	return "%s-%X" % (tail, abs(label.__hash__()))

