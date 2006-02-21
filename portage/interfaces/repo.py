# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id$

from portage.util.dependant_methods import ForcedDepends
from portage.util.currying import pre_curry

def decorate_ui_callback(stage, status_obj, original, *a, **kw):
	status_obj.phase(stage)
	return original(*a, **kw)


class fake_lock:
	def __init__(self): pass
	acquire_write_lock = acquire_read_lock = release_read_lock = release_write_lock = __init__


class base(object):
	__metaclass__ = ForcedDepends
	
	stage_depends = {}
	stage_hooks = []

	def __init__(self, repo, pkg, status_obj=None):
		self.repo = repo
		self.pkg = pkg
		self.underway = False
		self.op = pkg._repo_install_op()
		self.lock = getattr(repo, "lock")
		if self.lock is None:
			self.lock = fake_lock()
		self.status_obj = status_obj
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

	def finish(self):
		self.lock.release_write_lock()
		self.underway = False
		return True

	def __del__(self):
		if self.underway:
			print "warning: %s merge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()


class install(base):
	
	stage_depends = {"finish":"merge_metadata", "merge_metadata":"postinst", "postinst":"transfer", "transfer":"preinst"}
	stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]

	def preinst(self):
		self.underway = True
		self.lock.acquire_write_lock()
		try:
			r = self.op.preinst()
		except:
			self.lock.release_write_lock()
			raise
		return r

	def transfer(self):	
		raise NotImplementedError

	def postinst(self):
		return self.op.postinst()

	def merge_metadata(self):
		raise NotImplementedError


class uninstall(base):
	
	stage_depends = {"finish":"unmerge_metadata", "unmerge_metadata":"postrm", "postrm":"remove", "remove":"prerm"}
	stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]

	def prerm(self):
		self.underway = True
		self.lock.acquire_write_lock()
		try:
			r = self.op.prerm()
		except:
			self.lock.release_write_lock()
			raise
		return r

	def remove(self):
		raise NotImplementedError

	def postrm(self):
		return self.op.postrm()

	def unmerge_metadata(self):
		raise NotImplementedError
		

	
