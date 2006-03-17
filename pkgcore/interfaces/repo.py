# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.dependant_methods import ForcedDepends
from pkgcore.util.currying import pre_curry
from pkgcore.merge.engine import MergeEngine, errors as merge_errors

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

	def __init__(self, repo, pkg, status_obj=None, offset=None):
		self.repo = repo
		self.pkg = pkg
		self.underway = False
		self.offset = offset
		assert getattr(self, "_op_name", None)
		self.op = getattr(pkg, self._op_name)()
		self.lock = getattr(repo, "lock")
		if self.lock is None:
			self.lock = fake_lock()
		self.status_obj = status_obj
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

	def start(self, engine):
		self.me = engine
		self.underway = True
		self.lock.acquire_write_lock()
		self.me.sanity_check()
		return True

	def finish(self):
		self.me.final()
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

	def start(self):
		return base.start(self, MergeEngine.install(self.pkg, offset=self.offset))

	def preinst(self):
		return self.op.preinst()

	def transfer(self):
		for x in (self.me.pre_merge, self.me.merge, self.me.post_merge):
			try:
				x()
			except merge_errors.NonFatalModification, e:
				print "warning caught: %s" % e
		return True

	def postinst(self):
		return self.op.postinst()

	def merge_metadata(self):
		raise NotImplementedError


class uninstall(base):
	
	stage_depends = {"finish":"unmerge_metadata", "unmerge_metadata":"postrm", "postrm":"remove", "remove":"prerm",
		"prerm":"start"}
	stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
	_op_name = "_repo_uninstall_op"

	def start(self):
		return base.start(self, MergeEngine.uninstall(self.pkg, offset=self.offset))

	def prerm(self):
		return self.op.prerm()

	def remove(self):
		for x in (self.me.pre_unmerge, self.me.unmerge, self.me.post_unmerge):
			try:
				x()
			except merge_errors.NonFatalModification, e:
				print "warning caught: %s" % e
		return True

	def postrm(self):
		return self.op.postrm()

	def unmerge_metadata(self):
		raise NotImplementedError
		
	def __del__(self):
		if self.underway:
			print "warning: %s unmerge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()
			
			
class replace(install, uninstall):
	stage_depends = {"finish":"unmerge_metadata",
		"unmerge_metadata":"postrm", "postrm":"remove","remove":"prerm", "prerm":"merge_metadata", 
		"merge_metadata":"postinst", "postinst":"transfer","transfer":"preinst",
		"preinst":"start"}

	stage_hooks = ["merge_metadata", "unmerge_metadata", "postrm", "prerm", "postinst", "preinst",
		"unmerge_metadata", "merge_metadata"]
	_op_name = "_repo_replace_op"

	def __init__(self, repo, oldpkg, newpkg, status_obj=None, offset=None):
		base.__init__(self, repo, newpkg, status_obj=status_obj, offset=offset)
		self.oldpkg = oldpkg
		
	def start(self):
		return base.start(self, MergeEngine.replace(self.oldpkg, self.pkg, offset=self.offset))

	def __del__(self):
		if self.underway:
			print "warning: %s -> %s replacement was underway, but wasn't completed" % (self.oldpkg, self.pkg)
			self.lock.release_write_lock()
