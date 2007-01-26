# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
repository modifications (installing, removing, replacing)
"""

from pkgcore.util.dependant_methods import ForcedDepends
from pkgcore.merge.engine import MergeEngine, errors as merge_errors
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.log:logger ")


class fake_lock:
    def __init__(self):
        pass

    acquire_write_lock = acquire_read_lock = __init__
    release_read_lock = release_write_lock = __init__


class base(object):
    __metaclass__ = ForcedDepends

    stage_depends = {}

class Failure(Exception):
    pass


class nonlivefs_base(base):

    stage_depends = {'finish': '_notify_repo', '_notify_repo': 'modify_repo',
        'modify_repo':'start'}

    def __init__(self, repo, observer=None):
        self.repo = repo
        self.underway = False
        self.observer = observer
        self.lock = getattr(repo, "lock")
        if self.lock is None:
            self.lock = fake_lock()

    def start(self):
        self.underway = True
        self.lock.acquire_write_lock()
        return True

    def modify_repo(self):
        raise NotImplementedError(self, 'modify_repo')

    def _notify_repo(self):
        raise NotImplementedError(self, '_notify_repo')

    def finish(self):
        self._notify_repo()
        self.lock.release_write_lock()
        self.underway = False
        return True


class nonlivefs_install(nonlivefs_base):

    def __init__(self, repo, pkg, **kwds):
        nonlivefs_base.__init__(self, repo, **kwds)
        self.new_pkg = pkg

    def _notify_repo(self):
        self.repo.notify_add_package(self.new_pkg)


class nonlivefs_uninstall(nonlivefs_base):

    def __init__(self, repo, pkg, **kwds):
        nonlivefs_base.__init__(self, repo, **kwds)
        self.old_pkg = pkg

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)


class nonlivefs_replace(nonlivefs_install, nonlivefs_uninstall):

    def __init__(self, repo, oldpkg, newpkg, **kwds):
        # yes there is duplicate initialization here.
        nonlivefs_uninstall.__init__(self, repo, oldpkg, **kwds)
        nonlivefs_install.__init__(self, repo, newpkg, **kwds)

    def _notify_repo(self):
        nonlivefs_uninstall._notify_repo(self)
        nonlivefs_install._notify_repo(self)


class livefs_base(base):
    stage_hooks = []

    def __init__(self, repo, observer=None, offset=None):
        self.repo = repo
        self.underway = False
        self.offset = offset
        self.observer = observer
        self.get_op()
        self.lock = getattr(repo, "lock")
        if self.lock is None:
            self.lock = fake_lock()

    def customize_engine(self, engine):
        pass

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
            print "warning: %s merge was underway, but wasn't completed"
            self.lock.release_write_lock()


class livefs_install(livefs_base):

    """base interface for installing a pkg into a livefs repo.

    repositories should override as needed.
    """

    stage_depends = {
        "finish":"merge_metadata", "merge_metadata":"postinst",
        "postinst":"transfer", "transfer":"preinst", "preinst":"start"}
    stage_hooks = ["merge_metadata", "postinst", "preinst", "transfer"]
    install_op_name = "_repo_install_op"

    def __init__(self, repo, pkg, *args, **kwds):
        self.new_pkg = pkg
        livefs_base.__init__(self, repo, *args, **kwds)

    install_get_format_op_args_kwds = livefs_base._get_format_op_args_kwds

    def get_op(self):
        op_args, op_kwds = self.install_get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        self.install_op = getattr(self.new_pkg,
            self.install_op_name)(*op_args, **op_kwds)

    def start(self):
        """start the install transaction"""
        engine = MergeEngine.install(self.new_pkg, offset=self.offset,
            observer=self.observer)
        self.new_pkg.add_format_triggers(self, self.install_op, engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def preinst(self):
        """execute any pre-transfer steps required"""
        return self.install_op.preinst()

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
        return self.install_op.postinst()

    def merge_metadata(self):
        """merge pkg metadata to the repository.  Must be overrided"""
        raise NotImplementedError

    def finish(self):
        ret = self.install_op.finalize()
        if not ret:
            logger.warn("ignoring unexpected result from install finalize- "
                "%r" % ret)
        return livefs_base.finish(self)


class livefs_uninstall(livefs_base):

    """base interface for uninstalling a pkg from a livefs repo.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"unmerge_metadata", "unmerge_metadata":"postrm",
        "postrm":"remove", "remove":"prerm", "prerm":"start"}
    stage_hooks = ["merge_metadata", "postrm", "prerm", "remove"]
    uninstall_op_name = "_repo_uninstall_op"

    def __init__(self, repo, pkg, *args, **kwds):
        self.old_pkg = pkg
        livefs_base.__init__(self, repo, *args, **kwds)

    uninstall_get_format_op_args_kwds = livefs_base._get_format_op_args_kwds

    def get_op(self):
        op_args, op_kwds = self.uninstall_get_format_op_args_kwds()
        op_kwds["observer"] = self.observer
        self.uninstall_op = getattr(self.old_pkg,
            self.uninstall_op_name)(*op_args, **op_kwds)

    def start(self):
        """start the uninstall transaction"""
        engine = MergeEngine.uninstall(self.old_pkg, offset=self.offset,
            observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.uninstall_op, engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def prerm(self):
        """execute any pre-removal steps required"""
        return self.uninstall_op.prerm()

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
        return self.uninstall_op.postrm()

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)

    def unmerge_metadata(self):
        """unmerge pkg metadata from the repository.  Must be overrided."""
        raise NotImplementedError

    def finish(self):
        ret = self.uninstall_op.finalize()
        self.uninstall_op.cleanup(disable_observer=True)
        if not ret:
            logger.warn("ignoring unexpected result from uninstall finalize- "
                "%r" % ret)
        return livefs_base.finish(self)

    def __del__(self):
        if self.underway:
            print "warning: %s unmerge was underway, but wasn't completed" % \
                self.old_pkg
            self.lock.release_write_lock()


class livefs_replace(livefs_install, livefs_uninstall):

    """base interface for replacing a pkg in a livefs repo with another.

    Repositories should override as needed.
    """

    stage_depends = {
        "finish":"postinst", "postinst":"unmerge_metadata",
        "unmerge_metadata":"postrm", "postrm":"remove",
        "remove":"prerm", "prerm":"merge_metadata",
        "merge_metadata":"transfer",
        "transfer":"preinst", "preinst":"start"}

    stage_hooks = [
        "merge_metadata", "unmerge_metadata", "postrm", "prerm", "postinst",
        "preinst", "unmerge_metadata", "merge_metadata"]

    def __init__(self, repo, oldpkg, newpkg, **kwds):
        self.old_pkg = oldpkg
        self.new_pkg = newpkg
        livefs_base.__init__(self, repo, **kwds)

    def get_op(self):
        livefs_install.get_op(self)
        livefs_uninstall.get_op(self)

    def start(self):
        """start the transaction"""
        engine = MergeEngine.replace(self.old_pkg, self.new_pkg,
            offset=self.offset, observer=self.observer)
        self.old_pkg.add_format_triggers(self, self.uninstall_op, engine)
        self.new_pkg.add_format_triggers(self, self.install_op, engine)
        self.customize_engine(engine)
        return livefs_base.start(self, engine)

    def _notify_repo(self):
        self.repo.notify_remove_package(self.old_pkg)
        self.repo.notify_add_package(self.new_pkg)

    def finish(self):
        ret = self.install_op.finalize()
        if not ret:
            logger.warn("ignoring unexpected result from install finalize- "
                "%r" % ret)
        ret = self.uninstall_op.finalize()
        self.uninstall_op.cleanup(disable_observer=True)
        if not ret:
            logger.warn("ignoring unexpected result from uninstall finalize- "
                "%r" % ret)
        return livefs_base.finish(self)

    def __del__(self):
        if self.underway:
            print "warning: %s -> %s replacement was underway, " \
                "but wasn't completed" % (self.old_pkg, self.new_pkg)
            self.lock.release_write_lock()
