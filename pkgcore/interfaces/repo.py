# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository modifications (installing, removing, replacing)
"""

from pkgcore.util.dependant_methods import ForcedDepends
from pkgcore.util.currying import pre_curry
from pkgcore.merge.engine import MergeEngine, errors as merge_errors

def decorate_ui_callback(stage, status_obj, original, *a, **kw):
	status_obj.phase(stage)
	return original(*a, **kw)


class fake_lock:
	def __init__(self):
		pass
	
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
		assert bool(getattr(self, "_op_name", None))
		op_args, op_kwds = self._get_format_op_args_kwds()
		self.op = getattr(pkg, self._op_name)(*op_args, **op_kwds)
		self.lock = getattr(repo, "lock")
		if self.lock is None:
			self.lock = fake_lock()
		self.status_obj = status_obj
		if status_obj is not None:
			for x in self.stage_hooks:
				setattr(self, x, pre_curry(decorate_ui_callback, x, status_obj, getattr(self, x)))

	def _get_format_op_args_kwds(self):
		return (), {}

	def start(self, engine):
		self.me = engine
		self.underway = True
		self.lock.acquire_write_lock()
		self.me.sanity_check()
		return True

	def finish(self):
		"""finish the transaction"""
		self.me.final()
		self._notify_repo()
		self.lock.release_write_lock()
		self.underway = False
		return True

	def _modify_repo_cache(self):
		raise NotImplementedError

	def __del__(self):
		if self.underway:
			print "warning: %s merge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()


class install(base):
	
	"""base interface for installing a pkg from a repo; repositories should override as needed"""
	
	stage_depends = {"finish":"merge_metadata", "merge_metadata":"postinst", "postinst":"transfer", "transfer":"preinst",
		"preinst":"start"}
	stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]
	_op_name = "_repo_install_op"

	def start(self):
		"""start the install transaction"""
		return base.start(self, MergeEngine.install(self.pkg, offset=self.offset))

	def preinst(self):
		"""execute any pre-transfer steps required"""
		return self.op.preinst()

	def transfer(self):
		"""execute the actual transfer"""
		for x in (self.me.pre_merge, self.me.merge, self.me.post_merge):
			try:
				x()
			except merge_errors.NonFatalModification, e:
				print "warning caught: %s" % e
		return True

	def _notify_repo(self):
		self.repo.notify_add_package(self.pkg)

	def postinst(self):
		"""execute any post-transfer steps required"""
		return self.op.postinst()

	def merge_metadata(self):
		"""merge pkg metadata to the repository.  Must be overrided"""
		raise NotImplementedError


class uninstall(base):

	"""base interface for uninstalling a pkg from a repo; repositories should override as needed"""

	stage_depends = {"finish":"unmerge_metadata", "unmerge_metadata":"postrm", "postrm":"remove", "remove":"prerm",
		"prerm":"start"}
	stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
	_op_name = "_repo_uninstall_op"

	def start(self):
		"""start the uninstall transaction"""
		return base.start(self, MergeEngine.uninstall(self.pkg, offset=self.offset))

	def prerm(self):
		"""execute any pre-removal steps required"""
		return self.op.prerm()

	def remove(self):
		"""execute any removal steps required"""
		for x in (self.me.pre_unmerge, self.me.unmerge, self.me.post_unmerge):
			try:
				x()
			except merge_errors.NonFatalModification, e:
				print "warning caught: %s" % e
		return True

	def postrm(self):
		"""execute any post-removal steps required"""
		return self.op.postrm()

	def _notify_repo(self):
		self.repo.notify_remove_package(self.pkg)

	def unmerge_metadata(self):
		"""unmerge pkg metadata from the repository.  Must be overrided."""
		raise NotImplementedError

	def __del__(self):
		if self.underway:
			print "warning: %s unmerge was underway, but wasn't completed" % self.pkg
			self.lock.release_write_lock()


class replace(install, uninstall):

	"""base interface for replacing a pkg in a repo with another; repositories should override as needed"""

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
		"""start the transaction"""
		return base.start(self, MergeEngine.replace(self.oldpkg, self.pkg, offset=self.offset))

	def _notify_repo(self):
		self.repo.notify_remove_package(self.oldpkg)
		self.repo.notify_add_package(self.pkg)

	def __del__(self):
		if self.underway:
			print "warning: %s -> %s replacement was underway, but wasn't completed" % (self.oldpkg, self.pkg)
			self.lock.release_write_lock()
