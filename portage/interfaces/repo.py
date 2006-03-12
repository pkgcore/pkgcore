# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

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
		assert getattr(self, "_op_name", None)
		self.op = getattr(pkg, self._op_name)()
		self.lock = getattr(repo, "lock")
		if self.lock is None:
			self.lock = fake_lock()
		self.status_obj = status_obj
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

	def start(self):
		self.underway = True
		self.lock.acquire_write_lock()
		return True

	def finish(self):
		self.lock.release_write_lock()
		self.underway = False
		return True

	def __del__(self):
		if self.underway:
			print "warning: %s merge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()


class install(base):
	
	stage_depends = {"finish":"merge_metadata", "merge_metadata":"postinst", "postinst":"transfer", "transfer":"preinst", 
		"preinst":"start"}
	stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]
	_op_name = "_repo_install_op"

	def preinst(self):
		return self.op.preinst()

	def transfer(self):	
		raise NotImplementedError

	def postinst(self):
		return self.op.postinst()

	def merge_metadata(self):
		raise NotImplementedError


class uninstall(base):
	
	stage_depends = {"finish":"unmerge_metadata", "unmerge_metadata":"postrm", "postrm":"remove", "remove":"prerm",
		"prerm":"start"}
	stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
	_op_name = "_repo_uninstall_op"

	def prerm(self):
		return self.op.prerm()

	def remove(self):
		raise NotImplementedError

	def postrm(self):
		return self.op.postrm()

	def unmerge_metadata(self):
		raise NotImplementedError
		

class replace(install, uninstall):
	stage_depends = {"finish":"unmerge_metadata",
		"unmerge_metadata":"postrm", "postrm":"remove","remove":"prerm", "prerm":"merge_metadata", 
		"merge_metadata":"postinst", "postinst":"transfer","transfer":"preinst",
		"preinst":"start"}

	stage_hooks = ["merge_metadata", "unmerge_metadata", "postrm", "prerm", "postinst", "preinst",
		"unmerge_metadata", "merge_metadata"]
	_op_name = "_repo_replace_op"
