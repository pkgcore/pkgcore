# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

import os, stat, errno, shutil
from itertools import ifilter
from pkgcore.repository import prototype, errors

#needed to grab the PN
from pkgcore.package.cpv import CPV as cpv
from pkgcore.fs.util import ensure_dirs
from pkgcore.util.mappings import LazyValDict
from pkgcore.vdb.contents import ContentsFile
from pkgcore.plugins import get_plugin
from pkgcore.interfaces import repo as repo_interfaces
from pkgcore.interfaces.data_source import local_source
from pkgcore.spawn import spawn


class tree(prototype.tree):
	ebuild_format_magic = "ebuild_built"

	def __init__(self, location):
		super(tree,self).__init__()
		self.base = self.location = location
		try:
			st = os.lstat(self.base)
			if not stat.S_ISDIR(st.st_mode):
				raise errors.InitializationError("base not a dir: %s" % self.base)
			elif not st.st_mode & (os.X_OK|os.R_OK):
				raise errors.InitializationError("base lacks read/executable: %s" % self.base)

		except OSError:
			raise errors.InitializationError("lstat failed on base %s" % self.base)

		self.package_class = get_plugin("format", self.ebuild_format_magic)(self)

	def _get_categories(self, *optionalCategory):
		# return if optionalCategory is passed... cause it's not yet supported
		if optionalCategory:
			return {}
		try:
			try:	return tuple([x for x in os.listdir(self.base) \
				if stat.S_ISDIR(os.lstat(os.path.join(self.base,x)).st_mode)])

			except (OSError, IOError), e:
				raise KeyError("failed fetching categories: %s" % str(e))
		finally:
			pass

	def _get_packages(self, category):
		cpath = os.path.join(self.base,category.lstrip(os.path.sep))
		l=set()
		try:
			try:
				for x in os.listdir(cpath):
					if stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) and not x.endswith(".lockfile"):
						l.add(cpv(x).package)
				return tuple(l)

			except (OSError, IOError), e:
				raise KeyError("failed fetching packages for category %s: %s" % \
				(os.path.join(self.base,category.lstrip(os.path.sep)), str(e)))
		finally:
			pass

	def _get_versions(self, catpkg):
		pkg = catpkg.split("/")[-1]
		l=set()
		try:
			try:
				cpath=os.path.join(self.base, os.path.dirname(catpkg.lstrip("/").rstrip("/")))
				for x in os.listdir(cpath):
					# XXX: This matches foo to foo-bar-1.2.3 and creates an incorrect foo-1.2.3 in l
					# This sucks.  fix...
					if x.startswith(pkg) and x[len(pkg)+1].isdigit() and stat.S_ISDIR(os.stat(os.path.join(cpath,x)).st_mode) \
						and not x.endswith(".lockfile"):
						l.add(cpv(x).fullver)
				return tuple(l)
			except (OSError, IOError), e:
				raise KeyError("failed fetching packages for package %s: %s" % \
				(os.path.join(self.base,catpkg.lstrip(os.path.sep)), str(e)))
		finally:
			pass

	def _get_ebuild_path(self, pkg):
		s = "%s-%s" % (pkg.package, pkg.fullver)
		return os.path.join(self.base, pkg.category, s, s+".ebuild")

	_metadata_rewrites = {"depends":"DEPEND", "rdepends":"RDEPEND", "use":"USE", "eapi":"EAPI"}
	
	def _get_metadata(self, pkg):
		path = os.path.dirname(pkg.path)
		try:
			keys = [self._metadata_rewrites.get(x, x) for x in 
				filter(lambda x: x.isupper() and stat.S_ISREG(os.stat(path+os.path.sep+x).st_mode) and x!="CONTENTS", 
				os.listdir(path))]
			keys.extend(["environment","contents"])
		except OSError:
			return None

		def load_data(key):
			if key == "contents":
				data = ContentsFile(os.path.join(path, "CONTENTS"))
			elif key == "environment":
				fp=os.path.join(path, key)
				if not os.path.exists(fp):
					if not os.path.exists(fp+".bz2"):
						# icky.
						raise KeyError("environment: no environment file found")
					fp += ".bz2"
				data =local_source(fp)
			else:
				try:
					f = open(os.path.join(path, key))
				except (OSError, IOError):
					return None
				data = f.read()
				f.close()
				data = data.strip()
			return data

		return LazyValDict(keys, load_data)

	def notify_remove_pkg(self, pkg):
		remove_it = list(self.packages[pkg.category]) == 1
		prototype.tree.notify_remove_pkg(self, pkg)
		if remove_it:
			try:
				os.rmdir(os.path.join(self.base, pkg.category))
			except OSError, oe:
				if oe.errno != errno.ENOTEMPTY:
					raise
				# silently swallow it;
				del oe

	def _install(self, pkg, *a, **kw):
		# need to verify it's not in already...
		return install(self, pkg, *a, **kw)

	def _uninstall(self, pkg, *a, **kw):
		return uninstall(self, pkg, *a, **kw)

	def _replace(self, oldpkg, newpkg, *a, **kw):
		return replace(self, oldpkg, newpkg, *a, **kw)


class install(repo_interfaces.install):
	def __init__(self, repo, pkg, *a, **kw):
		self.dirpath = os.path.join(repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
		repo_interfaces.install.__init__(self, repo, pkg, *a, **kw)
		
	def merge_metadata(self, dirpath=None):
		# error checking?
		if dirpath is None:
			dirpath = self.dirpath
		ensure_dirs(dirpath)
		rewrite = self.repo._metadata_rewrites
		for k in self.pkg.tracked_attributes:
			if k == "contents":
				v = ContentsFile(os.path.join(dirpath, "CONTENTS"), writable=True, empty=True)
				for x in self.pkg.contents:
					if self.offset:
						v.add(x.change_location(os.path.join(self.offset, x.location)))
					else:
						v.add(x)
				v.flush()
			elif k == "environment":
				shutil.copy(getattr(self.pkg, k).get_path(), os.path.join(dirpath, "environment"))
				spawn(["bzip2", "-9", os.path.join(dirpath, "environment")], fd_pipes={})
			else:
				v = getattr(self.pkg, k)
				if not isinstance(v, basestring):
					try:
						s = ' '.join(v)
					except TypeError:
						s = str(v)
				else:
					s = v
				if not s.endswith("\n"):
					s += "\n"
				open(os.path.join(dirpath, rewrite.get(k, k.upper())), "w").write(s)
		return True


class uninstall(repo_interfaces.uninstall):
	def __init__(self, repo, pkg, offset=None, *a, **kw):
		self.dirpath = os.path.join(repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
		repo_interfaces.uninstall.__init__(self, repo, pkg, offset=offset, *a, **kw)

	def unmerge_metadata(self, dirpath=None):
		if dirpath is None:
			dirpath = self.dirpath
		shutil.rmtree(self.dirpath)
		return True

# should convert these to mixins.
class replace(install, uninstall, repo_interfaces.replace):
	
	def __init__(self, repo, pkg, *a, **kw):
		self.dirpath = os.path.join(repo.base, pkg.category, pkg.package+"-"+pkg.fullver)
		self.tmpdirpath = os.path.join(os.path.dirname(self.dirpath), ".tmp."+os.path.basename(self.dirpath))
		repo_interfaces.replace.__init__(self, repo, pkg, *a, **kw)
	
	def merge_metadata(self, *a, **kw):
		kw["dirpath"] = self.tmpdirpath
		return install.merge_metadata(self, *a, **kw)
	
	def unmerge_metadata(self, *a, **kw):
		ret = uninstall.unmerge_metadata(self, *a, **kw)
		if not ret:
			return ret
		os.rename(self.tmpdirpath, self.dirpath)
		return True
