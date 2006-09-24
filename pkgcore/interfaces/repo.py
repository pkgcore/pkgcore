# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository modifications (installing, removing, replacing)
"""

from pkgcore.util.dependant_methods import ForcedDepends
from pkgcore.util.currying import partial
from pkgcore.merge.engine import MergeEngine, errors as merge_errors


class fake_lock:
    def __init__(self):
        pass

    acquire_write_lock = acquire_read_lock = __init__
    release_read_lock = release_write_lock = __init__


class base(object):
    __metaclass__ = ForcedDepends

    stage_depends = {}
    stage_hooks = []

    def __init__(self, repo, observer=None, offset=None):
        self.repo = repo
        self.underway = False
        self.offset = offset
        self.observer = observer
        self.op = self._get_op()
        self.lock = getattr(repo, "lock")
        if self.lock is None:
            self.lock = fake_lock()

    def _get_format_op_args_kwds(self):
        return (), {}

    def start(self, engine):
        # add the pkgs triggers.
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
            print "warning: %s merge was underway, but wasn't completed"
            self.lock.release_write_lock()


class install(base):

    """base interface for installing a pkg from a repo.

    repositories should override as needed.
    """

    stage_depends = {
        "finish":"merge_metadata", "merge_metadata":"postinst",
        "postinst":"transfer", "transfer":"preinst", "preinst":"start"}
    stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]
    _op_name = "_repo_install_op"

    def __init__(self, repo, pkg, *args, **kwds):
        self.new_pkg = pkg
        base.__init__(self, repo, *args, **kwds)

    def _get_op(self):
        assert bool(getattr(self, "_op_name", None))
        op_args, op_kwds = self._get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        return getattr(self.new_pkg, self._op_name)(*op_args, **op_kwds)

    def start(self):
        """start the install transaction"""
        engine = MergeEngine.install(self.new_pkg, offset=self.offset,
            observer=self.observer)
        self.new_pkg.add_format_triggers(self, self.op, engine)
        return base.start(self, engine)

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
        self.repo.notify_add_package(self.new_pkg)

    def postinst(self):
        """execute any post-transfer steps required"""
        return self.op.postinst()

    def merge_metadata(self):
        """merge pkg metadata to the repository.  Must be overrided"""
        raise NotImplementedError


class uninstall(base):

    """base interface for uninstalling a pkg from a repo.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"unmerge_metadata", "unmerge_metadata":"postrm",
        "postrm":"remove", "remove":"prerm", "prerm":"start"}
    stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
    _op_name = "_repo_uninstall_op"

    def __init__(self, repo, pkg, *args, **kwds):
        self.old_pkg = pkg
        base.__init__(self, repo, *args, **kwds)
    
    def _get_op(self):
        assert bool(getattr(self, "_op_name", None))
        op_args, op_kwds = self._get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        return getattr(self.old_pkg, self._op_name)(*op_args, **op_kwds)

    def start(self):
        """start the uninstall transaction"""
        engine = MergeEngine.uninstall(self.old_pkg, offset=self.offset,
            observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.op, engine)
        return base.start(self, engine)

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
        self.repo.notify_remove_package(self.old_pkg)

    def unmerge_metadata(self):
        """unmerge pkg metadata from the repository.  Must be overrided."""
        raise NotImplementedError

    def __del__(self):
        if self.underway:
            print "warning: %s unmerge was underway, but wasn't completed" % \
                self.old_pkg
            self.lock.release_write_lock()


class replace(install, uninstall):

    """base interface for replacing a pkg in a repo with another.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"unmerge_metadata", "unmerge_metadata":"postrm",
        "postrm":"remove","remove":"prerm", "prerm":"merge_metadata",
        "merge_metadata":"postinst", "postinst":"transfer",
        "transfer":"preinst", "preinst":"start"}

    stage_hooks = [
        "merge_metadata", "unmerge_metadata", "postrm", "prerm", "postinst",
        "preinst", "unmerge_metadata", "merge_metadata"]
    _op_name = "_repo_replace_op"

    def __init__(self, repo, oldpkg, newpkg, **kwds):
        self.old_pkg = oldpkg
        self.new_pkg = newpkg
        base.__init__(self, repo, **kwds)
    
    _get_op = install._get_op

    def start(self):
        """start the transaction"""
        engine = MergeEngine.replace(self.old_pkg, self.new_pkg,
            offset=self.offset, observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.op, engine)
        self.new_pkg.add_format_triggers(self, self.op, engine)
        return base.start(self, engine)

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)
        self.repo.notify_add_package(self.new_pkg)

    def __del__(self):
        if self.underway:
            print "warning: %s -> %s replacement was underway, " \
                "but wasn't completed" % (self.old_pkg, self.new_pkg)
            self.lock.release_write_lock()
