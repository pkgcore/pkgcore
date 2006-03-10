# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id:$

import os
from portage.fs.contents import contentsSet
from portage.fs import fs

class ContentsFile(contentsSet):
	"""class wrapping a contents file"""

	def __init__(self, location, writable=False, empty=False):
		contentsSet.__init__(self)
		self._file_location = location
		if not empty:
			self.readonly = False
			self._read()
			
		self.readonly = not writable


	def add(self, obj):
		if self.readonly:
			raise TypeError("This instance is readonly")
		elif isinstance(obj, fs.fsFile):
			# strict checks
			if obj.chksums == None or "md5" not in obj.chksums:
				raise TypeError("fsFile objects need to be strict")
		elif not isinstance(obj, (fs.fsDir, fs.fsLink, fs.fsFifo, fs.fsDev)):
			raise TypeError("obj must be of fsObj, fsDir, fsLink, fsFifo, fsDev class or derivative")
		
		contentsSet.add(self, obj)


	def remove(self, key):
		if self.readonly:
			raise TypeError("This instance is readonly")
		contentsSet.remove(self, key)


	def clear(self):
		if self.readonly:
			raise TypeError("This instance is readonly")
		contentsSet.clear(self)


	def flush(self):
		return self._write()


	def _parse_old(self, line):
		"""parse old contents, non tab based format"""
		s = line.split()
		if s[0] in ("dir","dev","fif"):
			return s[0], ' '.join(s[1:])
		elif s[0] == "obj":
			return "obj", ' '.join(s[1:-2]), s[-2], s[-1]
		elif s[0] == "sym":
			try:
				p = s.index("->")
				return "sym", ' '.join(s[1:p]), ' '.join(s[p+1:-1]), long(s[-1])

			except ValueError:
				# XXX throw a corruption error
				raise
		else:
			return s[0], ' '.join(s[1:])


	def _read(self):
		self.clear()
		try:
			infile = open(self._file_location, "r")
			for line in infile:
				if "\t" not in line:
					line = self._parse_old(line.strip("\n"))
				else:
					line = line.strip("\n").split("\t")

				if line[0] == "dir":
					obj = fs.fsDir(line[1], strict=False)
				elif line[0] == "fif":
					obj = fs.fsDir(line[1], strict=False)
				elif line[0] == "dev":
					obj = fs.fsDev(line[1], strict=False)
				elif line[0] == "obj":
					#file: path, md5, time
					obj = fs.fsFile(line[1], chksums={"md5":line[2]}, mtime=line[3], strict=False)
				elif line[0] == "sym":
					#path, target, ' -> ', mtime
					obj = fs.fsLink(line[1],line[2], mtime=line[3], strict=False)
				else:
					if len(line) > 2:
						line = line[0], ' '.join(line[1:])
					raise Exception("unknown entry type %s: %s" % (line[0], line[1]))
				self.add(obj)

		finally:
			try:	infile.close()
			except UnboundLocalError:
				pass


	def _write(self):
		try:
			outfile = open(self._file_location + ".temp","w")

			for obj in self:

				if isinstance(obj, fs.fsFile):
					s = "\t".join(("obj", obj.location, obj.chksums["md5"], str(obj.mtime)))

				elif isinstance(obj, fs.fsLink):
					# write the tab, *and spaces*.  tab's for delimiting.
					# spaces are for backwards compatability
					s = "\t".join(("sym", obj.location, " -> ", obj.target, str(obj.mtime)))

				elif isinstance(obj, fs.fsDir):
					s = "dir\t" + obj.location

				elif isinstance(obj, fs.fsDev):
					s = "dev\t" + obj.location

				elif isinstance(obj, fs.fsFifo):
					s = "fif\t" + obj.location

				else:
					raise Exception("unknown type %s: %s" % (type(obj),str(obj)))
				outfile.write(s + "\n")

		except Exception, e:
			try:	outfile.close()
			except (IOError, OSError): pass
			try:	os.remove(self._file_location + ".temp")
			except (IOError, OSError): pass
			raise
		else:
			try:
				outfile.close()
				os.rename(self._file_location + ".temp", self._file_location)
			except (OSError, IOError), e:
				# XXX what to do?
				try:	os.remove(self.__file+".temp")
				except (OSError, IOError): pass
				raise

