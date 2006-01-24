# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id$

from portage.operations.dependant_methods import ForcedDepends
from portage.util.currying import pre_curry

class base(object):

	__metaclass__ = ForcedDepends
	

	def __init__(self, pkg):
		self.package = pkg
	
	def repo_lock(self):
		raise NotImplementedError
	
	repo_unlock = repo_lock
	update_repo = repo_lock

	def run():
		return True
		

def decorate_ui_callback(stage, status_obj, original, *a, **kw):
	status_obj.phase(stage)
	return original(*a, **kw)

class install(object):
	__metaclass__ = ForcedDepends
	
	stage_depends = {"finish":"merge_metadata", "merge_metadata":"postinst", "postinst":"transfer", "transfer":"preinst"}
	stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]

	def __init__(self, pkg, repo_lock, status_obj=None):
		self.pkg = pkg
		self.op = pkg._repo_install()
		self.lock = repo_lock
		self.underway = False
		self.status_obj = status_obj
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

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
		
	def finish(self):
		self.lock.release_write_lock()
		self.underway = False
		return True

	def __del__(self):
		if self.underway:
			print "warning: %s merge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()


class uninstall(base):

	stage_depends = {"finish":"unmerge_metadata", "unmerge_metadata":"postrm", "postrm":"remove", "remove":"prerm"}

	def __init__(self, pkg, repo_lock, status_obj=None):
		self.pkg = pkg
		self.lock = repo_lock
		self.underway = False
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

	def prerm(self):
		self.underway = True
		self.lock.acquire_write_lock()
		try:
			self.format.prerm()
		except:
			self.lock.release_write_lock()
			raise
		return True
	
	def unmerge_metadata(self):
		raise NotImplementedError

	def postrm(self):
		self.format.postrm()

	def run(self):
		return self.finish()
	
	def finish(self):
		self.lock.release_write_lock()
		self.underway = False

	def __del__(self):
		if self.underway:
			self.lock.release_write_lock()
		
