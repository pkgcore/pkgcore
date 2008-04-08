# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
EBuild Daemon (ebd), main high level interface to ebuild execution env
(ebuild.sh being part of it).

Wraps L{pkgcore.ebuild.processor} functionality into a higher level
api, per phase methods for example
"""


import os, errno, shutil

from pkgcore.interfaces import format, data_source
from pkgcore.ebuild.processor import \
    request_ebuild_processor, release_ebuild_processor, \
    expected_ebuild_env, chuck_UnhandledCommand
from pkgcore.os_data import portage_gid, portage_uid
from pkgcore.spawn import (
    spawn_bash, spawn, is_sandbox_capable, is_fakeroot_capable)
from pkgcore.os_data import xargs
from pkgcore.ebuild.const import eapi_capable
from pkgcore.interfaces import observer
from pkgcore.ebuild.ebuild_built import fake_package_factory, package
from snakeoil.currying import post_curry, pretty_docs
from snakeoil.osutils import ensure_dirs, normpath, join as pjoin

from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.log:logger",
    "pkgcore.package.mutated:MutatedPkg",
)


def _reset_env_data_source(method):
    return method

    # unreachable code. --charlie
    #def store_env_data_wrapper(self, *args, **kwds):
    #    try:
    #        return method(self, *args, **kwds)
    #    finally:
    #        # note that we're *not* return'ing anything ourselves.
    #        # we want the original val to slide back
    #        if self.env_data_source is None:
    #            try:
    #                fp = self.env["PORT_ENV_FILE"]
    #                f = self.env_data.get_fileobj()
    #                f.seek(0, 0)
    #                f.truncate(0)
    #                f.write(open(fp, "r").read())
    #                del f, fp
    #            except (IOError, OSError), oe:
    #                if oe.errno != errno.ENOENT:
    #                    raise

    #store_env_data_wrapper.__doc__ = method.__doc__
    #return store_env_data_wrapper


class ebd(object):

    def __init__(self, pkg, initial_env=None, env_data_source=None,
                 features=None, observer=None, clean=False, tmp_offset=None):
        """
        @param pkg:
            L{ebuild package instance<pkgcore.ebuild.ebuild_src.package>}
            instance this env is being setup for
        @param initial_env: initial environment to use for this ebuild
        @param env_data_source: a L{pkgcore.interfaces.data_source} instance
            to restore the environment from- used for restoring the
            state of an ebuild processing, whether for unmerging, or
            walking phases during building
        @param features: ebuild features, hold over from portage,
            will be broken down at some point
        """

        if not hasattr(self, "observer"):
            self.observer = observer
        if pkg.eapi not in eapi_capable:
            raise TypeError(
                "pkg isn't of a supported eapi!, %i not in %s for %s" % (
                    pkg.eapi, eapi_capable, pkg))

        if initial_env is not None:
            # copy.
            self.env = dict(initial_env)
            for x in ("USE", "ACCEPT_LICENSE"):
                if x in self.env:
                    del self.env[x]
        else:
            self.env = {}

        # temp hack.
        for x in ('chost', 'cbuild', 'ctarget'):
            val = getattr(pkg, x)
            if val is not None:
                self.env[x.upper()] = val
            
        if "PYTHONPATH" in os.environ:
            self.env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        if "PKGCORE_DEBUG" in os.environ:
            self.env["PKGCORE_DEBUG"] = str(int(os.environ["PKGCORE_DEBUG"]))

        self.env.setdefault("ROOT", "/")
        self.env_data_source = env_data_source
        if env_data_source is not None and \
            not isinstance(env_data_source, data_source.base):
            raise TypeError(
                "env_data_source must be None, or a pkgcore.data_source.base "
                "derivative: %s: %s" % (
                    env_data_source.__class__, env_data_source))

        if features is None:
            features = self.env.get("FEATURES", ())

        self.features = set(x.lower() for x in features)

        self.env["FEATURES"] = ' '.join(sorted(self.features))

        expected_ebuild_env(pkg, self.env, env_source_override=self.env_data_source)

        self.env["USE"] = ' '.join(str(x) for x in pkg.use)
        self.env["INHERITED"] = ' '.join(pkg.data.get("_eclasses_", ()))
        self.env["SLOT"] = pkg.slot
        self.env["FINALIZED_RESTRICT"] = ' '.join(str(x) for x in pkg.restrict)

        self.restrict = pkg.restrict

        for x in ("sandbox", "userpriv", "fakeroot"):
            setattr(self, x, self.feat_or_bool(x) and not (x in self.restrict))
        if self.fakeroot:
            logger.warn("disabling fakeroot; unusable till coreutils/fakeroot" +
                " interaction is fixed")
            self.fakeroot = False
        if self.userpriv and os.getuid() != 0:
            self.userpriv = False

        if "PORT_LOGDIR" in self.env:
            self.logging = pjoin(self.env["PORT_LOGDIR"],
                                        pkg.cpvstr+".log")
            del self.env["PORT_LOGDIR"]
        else:
            self.logging = False

        self.env["XARGS"] = xargs

        self.bashrc = self.env.get("bashrc", ())
        if self.bashrc:
            del self.env["bashrc"]

        self.pkg = pkg
        self.eapi = pkg.eapi
        wipes = [k for k, v in self.env.iteritems()
                 if not isinstance(v, basestring)]
        for k in wipes:
            del self.env[k]
        del wipes, k, v

        self.set_op_vars(tmp_offset)
        self.clean_at_start = clean
        self.clean_needed = False

    def start(self):
        if self.clean_at_start:
            self.clean_needed = True
            if not self.cleanup():
                return False
        self.setup_workdir()
        self.setup_env_data_source()
        self.clean_needed = True
        return True

    def set_op_vars(self, tmp_offset):
        # don't fool with this, without fooling with setup.
        self.base_tmpdir = self.env["PORTAGE_TMPDIR"]
        self.tmpdir = normpath(pjoin(self.base_tmpdir, "portage"))
        if tmp_offset:
            self.tmpdir = pjoin(self.tmpdir,
                tmp_offset.strip(os.path.sep))

        self.builddir = pjoin(self.tmpdir, self.env["CATEGORY"],
            self.env["PF"])
        for x, y in (("T", "temp"), ("WORKDIR", "work"), ("D", "image"),
            ("HOME", "homedir")):
            self.env[x] = pjoin(self.builddir, y) +"/"

        self.env["IMAGE"] = self.env["D"]

    def get_env_source(self):
        return data_source.data_source(
            open(pjoin(self.env["T"], "environment"), "r").read())

    def setup_env_data_source(self):
        if not ensure_dirs(self.env["T"], mode=0770, gid=portage_gid,
            minimal=True):
            raise format.FailedDirectory(self.env['T'],
                "%s doesn't fulfill minimum mode %o and gid %i" % (
                self.env['T'], 0770, portage_gid))

        if self.env_data_source is not None:
            fp = pjoin(self.env["T"], "environment")
            # load data first (might be a local_source), *then* right
            # if it's a src_ebuild being installed, trying to do two steps
            # stomps the local_sources data.
            data = self.env_data_source.get_fileobj().read()
            open(fp, "w").write(data)
            del data

    def setup_logging(self):
        if self.logging and not ensure_dirs(os.path.dirname(self.logging),
                                            mode=02770, gid=portage_gid):
            raise format.FailedDirectory(
                os.path.dirname(self.logging),
                "PORT_LOGDIR, desired mode 02770 and gid %i" % portage_gid)

    def setup_workdir(self):
        # ensure dirs.
        for k in ("HOME", "T", "WORKDIR", "D"):
            if not ensure_dirs(self.env[k], mode=04770,
                gid=portage_gid, minimal=True):
                raise format.FailedDirectory(
                    self.env[k],
                    "%s doesn't fulfill minimum mode %o and gid %i" % (
                        k, 0770, portage_gid))
            # XXX hack, just 'til pkgcore controls these directories
            if (os.stat(self.env[k]).st_mode & 02000):
                logger.warn("%s ( %s ) is setgid" % (self.env[k], k))


    @_reset_env_data_source
    def _generic_phase(self, phase, userpriv, sandbox, fakeroot,
                       extra_handlers=None):
        """
        @param phase: phase to execute
        @param userpriv: will we drop to
            L{portage_uid<pkgcore.os_data.portage_uid>} and
            L{portage_gid<pkgcore.os_data.portage_gid>} access for this phase?
        @param sandbox: should this phase be sandboxed?
        @param fakeroot: should the phase be fakeroot'd?  Only really useful
            for install phase, and is mutually exclusive with sandbox
        """
        ebd = request_ebuild_processor(userpriv=(self.userpriv and userpriv),
            sandbox=(self.sandbox and sandbox and is_sandbox_capable()),
            fakeroot=(self.fakeroot and fakeroot and is_fakeroot_capable()))
        try:
            ebd.prep_phase(phase, self.env, sandbox=self.sandbox,
                           logging=self.logging)
            ebd.write("start_processing")
            if not ebd.generic_handler(additional_commands=extra_handlers):
                raise format.GenericBuildError(
                    phase + ": Failed building (False/0 return from handler)")

        except Exception, e:
            ebd.shutdown_processor()
            release_ebuild_processor(ebd)
            if isinstance(e, (SystemExit, format.GenericBuildError)):
                raise
            raise format.GenericBuildError(
                phase + ": Caught exception while building: %s" % e)

        release_ebuild_processor(ebd)
        return True

    def cleanup(self, disable_observer=False):
        if not self.clean_needed or not os.path.exists(self.builddir):
            return True
        if disable_observer:
            return self.do_cleanup(disable_observer=disable_observer)
        return self.do_cleanup()

    @observer.decorate_build_method("cleanup")
    def do_cleanup(self):
        try:
            shutil.rmtree(self.builddir)
            # try to wipe the cat dir; if not empty, ignore it
            try:
                os.rmdir(os.path.dirname(self.builddir))
            except OSError, e:
                if e.errno != errno.ENOTEMPTY:
                    raise
        except OSError, oe:
            raise format.GenericBuildError(
                "clean: Caught exception while cleansing: %s" % oe)
        return True

    def feat_or_bool(self, name, extra_env=None):
        if name in self.env:
            v = bool(self.env[name])
            del self.env[name]
            name = name.lower()
            if v:
                self.features.add(name)
            else:
                if name in self.features:
                    self.features.remove(name)
        elif extra_env is not None and name in extra_env:
            v = bool(extra_env[name])
            if v:
                self.features.add(name.lower())
            else:
                self.features.remove(name.lower())
        else:
            v = name.lower() in self.features
        return v


class setup_mixin(object):

    setup_is_for_src = True

    def setup(self,  setup_phase_override=None):
        self.setup_logging()

        additional_commands = {}
        phase_name = "setup-binpkg"
        if self.setup_is_for_src:
            phase_name = "setup"
        if setup_phase_override is not None:
            phase_name = setup_phase_override

        ebdp = request_ebuild_processor(userpriv=False, sandbox=False)
        if self.setup_is_for_src:
            additional_commands["request_inherit"] = \
                post_curry(ebdp.__class__._inherit, self.eclass_cache)
            additional_commands["request_profiles"] = self._request_bashrcs

        try:
            ebdp.prep_phase(phase_name, self.env, sandbox=self.sandbox,
                logging=self.logging)
            ebdp.write("start_processing")
            if not ebdp.generic_handler(
                additional_commands=additional_commands):
                raise format.GenericBuildError(
                    "setup: Failed building (False/0 return from handler)")

        except Exception, e:
            # regardless of what occured, we kill the processor.
            ebdp.shutdown_processor()
            release_ebuild_processor(ebdp)
            # either we know what it is, or it's a shutdown.  re-raise
            if isinstance(e, (SystemExit, format.GenericBuildError)):
                raise
            # wrap.
            raise format.GenericBuildError(
                "setup: Caught exception while building: " + str(e))

        release_ebuild_processor(ebdp)
        return True

    def _request_bashrcs(self, ebd, a):
        if a is not None:
            chuck_UnhandledCommand(ebd, "bashrc request with arg"+str(a))
        for source in self.bashrc:
            if source.get_path is not None:
                ebd.write("path\n%s" % source.get_path())
            elif source.get_data is not None:
                raise NotImplementedError
            else:
                chuck_UnhandledCommand(
                    ebd, "bashrc request: unable to process bashrc "
                    "due to source '%s' due to lacking usable get_*" % (
                        source,))
            if not ebd.expect("next"):
                chuck_UnhandledCommand(
                    ebd, "bashrc transfer, didn't receive 'next' response.  "
                    "failure?")
        ebd.write("end_request")


class install_op(ebd, format.install):
    """
    phase operations and steps for install execution
    """

    preinst = pretty_docs(
        observer.decorate_build_method("preinst")(
            post_curry(
            ebd._generic_phase, "preinst", False, False, False)),
            "run the postinst phase")
    postinst = pretty_docs(
        observer.decorate_build_method("postinst")(
            post_curry(
            ebd._generic_phase, "postinst", False, False, False)),
            "run the postinst phase")


class uninstall_op(ebd, format.uninstall):
    """
    phase operations and steps for uninstall execution
    """

    def __init__(self, *args, **kwargs):
        kwargs["tmp_offset"] = "unmerge"
        ebd.__init__(self, *args, **kwargs)

    prerm = pretty_docs(
        observer.decorate_build_method("prerm")(
            post_curry(
            ebd._generic_phase, "prerm", False, False, False)),
            "run the prerm phase")
    postrm = pretty_docs(
        observer.decorate_build_method("postrm")(
            post_curry(
            ebd._generic_phase, "postrm", False, False, False)),
            "run the postrm phase")


class replace_op(format.replace, install_op, uninstall_op):
    def __init__(self, *args, **kwargs):
        ebd.__init__(self, *args, **kwargs)


class buildable(ebd, setup_mixin, format.build):

    """
    build operation
    """

    _built_class = package

    # XXX this is unclean- should be handing in strictly what is build
    # env, rather then dumping domain settings as env.
    def __init__(self, pkg, domain_settings, eclass_cache, fetcher,
        observer=None, **kwargs):

        """
        @param pkg: L{pkgcore.ebuild.ebuild_src.package} instance we'll be
            building
        @param domain_settings: dict bled down from the domain configuration;
            basically initial env
        @param eclass_cache: the L{eclass_cache<pkgcore.ebuild.eclass_cache>}
            we'll be using
        @param fetcher: a L{pkgcore.fetch.base.fetcher} instance to use to
            access our required files for building
        """

        format.build.__init__(self, observer=observer)
        ebd.__init__(self, pkg, initial_env=domain_settings,
                     features=domain_settings["FEATURES"], **kwargs)

        self.env["FILESDIR"] = pjoin(os.path.dirname(pkg.ebuild.get_path()), "files")
        self.eclass_cache = eclass_cache
        self.env["ECLASSDIR"] = eclass_cache.eclassdir
        self.env["PORTDIR"] = eclass_cache.portdir

        self.fetcher = fetcher

        self.run_test = self.feat_or_bool("test", domain_settings)
        if "test" in self.restrict:
            self.run_test = False
        elif "test" not in pkg.use:
            if self.run_test:
                logger.warn("disabling test for %s due to test use flag being disabled" % pkg)
            self.run_test = False

        # XXX minor hack
        path = self.env["PATH"].split(":")

        for s, default in (("DISTCC", ".distcc"), ("CCACHE", "ccache")):
            b = (self.feat_or_bool(s, domain_settings)
                 and not s in self.restrict)
            setattr(self, s.lower(), b)
            if b:
                # looks weird I realize, but
                # pjoin("/foor/bar", "/barr/foo") == "/barr/foo"
                # and pjoin("/foo/bar",".asdf") == "/foo/bar/.asdf"
                self.env.setdefault(s+"_DIR", pjoin(self.tmpdir, default))
                path.insert(0, "/usr/lib/%s/bin" % s.lower())
            else:
                for y in ("_PATH", "_DIR"):
                    if s+y in self.env:
                        del self.env[s+y]
        path = [piece for piece in path if piece]
        self.env["PATH"] = ":".join(path)
        self.fetchables = pkg.fetchables[:]
        self.env["A"] = ' '.join(set(x.filename
            for x in self.fetchables))

        if self.setup_is_for_src:
            self.init_distfiles_env()

    def init_distfiles_env(self):
        # cvs/svn ebuilds need to die.
        distdir_write = self.fetcher.get_storage_path()
        if distdir_write is None:
            raise format.GenericBuildError("no usable distdir was found "
                "for PORTAGE_ACTUAL_DISTDIR from fetcher %s" % self.fetcher)
        self.env["PORTAGE_ACTUAL_DISTDIR"] = distdir_write
        self.env["DISTDIR"] = normpath(
            pjoin(self.builddir, "distdir"))
        for x in ("PORTAGE_ACTUAL_DISTDIR", "DISTDIR"):
            self.env[x] = os.path.realpath(self.env[x]).rstrip("/") + "/"

    def setup_distfiles(self):
        # added to protect against no-auto usage in pebuild.
        if not hasattr(self, 'files'):
            self.fetch()

        if self.files:
            try:
                if os.path.exists(self.env["DISTDIR"]):
                    if (os.path.isdir(self.env["DISTDIR"])
                        and not os.path.islink(self.env["DISTDIR"])):
                        shutil.rmtree(self.env["DISTDIR"])
                    else:
                        os.unlink(self.env["DISTDIR"])

            except OSError, oe:
                raise format.FailedDirectory(
                    self.env["DISTDIR"],
                    "failed removing existing file/dir/link at: exception %s"
                    % oe)

            if not ensure_dirs(self.env["DISTDIR"], mode=0770,
                               gid=portage_gid):
                raise format.FailedDirectory(
                    self.env["DISTDIR"],
                    "failed creating distdir symlink directory")

            try:
                for src, dest in [
                    (k, pjoin(self.env["DISTDIR"], v.filename))
                    for (k, v) in self.files.items()]:
                    os.symlink(src, dest)

            except OSError, oe:
                raise format.GenericBuildError(
                    "Failed symlinking in distfiles for src %s -> %s: %s" % (
                        src, dest, str(oe)))

    @observer.decorate_build_method("setup")
    def setup(self):
        """
        execute the setup phase, mapping out to pkg_setup in the ebuild

        necessarily dirs are created as required, and build env is
        initialized at this point
        """
        if self.distcc:
            for p in ("", "/lock", "/state"):
                if not ensure_dirs(pjoin(self.env["DISTCC_DIR"], p),
                                   mode=02775, gid=portage_gid):
                    raise format.FailedDirectory(
                        pjoin(self.env["DISTCC_DIR"], p),
                        "failed creating needed distcc directory")
        if self.ccache:
            # yuck.
            st = None
            try:
                st = os.stat(self.env["CCACHE_DIR"])
            except OSError:
                st = None
                if not ensure_dirs(self.env["CCACHE_DIR"], mode=02775,
                                   gid=portage_gid):
                    raise format.FailedDirectory(
                        self.env["CCACHE_DIR"],
                        "failed creation of ccache dir")

                # XXX this is more then mildly stupid.
                st = os.stat(self.env["CCACHE_DIR"])
            try:
                if st.st_gid != portage_gid or (st.st_mode & 02775) != 02775:
                    try:
                        cwd = os.getcwd()
                    except OSError:
                        cwd = "/"
                    try:
                        # crap.
                        os.chmod(self.env["CCACHE_DIR"], 02775)
                        os.chown(self.env["CCACHE_DIR"], -1, portage_gid)
                        os.chdir(cwd)
                        if 0 != spawn(["chgrp", "-R", str(portage_gid),
                            self.env["CCACHE_DIR"]]):
                            raise format.FailedDirectory(
                                self.env["CCACHE_DIR"],
                                "failed changing ownership for CCACHE_DIR")
                        if 0 != spawn_bash(
                            "find '%s' -type d -print0 | %s --null chmod 02775"
                                % (self.env["CCACHE_DIR"], xargs)):
                            raise format.FailedDirectory(
                                self.env["CCACHE_DIR"],
                                "failed correcting perms for CCACHE_DIR")

                        if 0 != spawn_bash(
                            "find '%s' -type f -print0 | %s --null chmod 0775"
                                % (self.env["CCACHE_DIR"], xargs)):
                            raise format.FailedDirectory(
                                self.env["CCACHE_DIR"],
                                "failed correcting perms for CCACHE_DIR")
                    finally:
                        os.chdir(cwd)
            except OSError:
                raise format.FailedDirectory(
                    self.env["CCACHE_DIR"],
                    "failed ensuring perms/group owner for CCACHE_DIR")
        return setup_mixin.setup(self)

    def configure(self):
        """
        execute the configure phase.

        does nothing if the pkg is EAPI=0 (that spec lacks a seperated
        configure phase).
        """
        if self.eapi > 1:
            return self._generic_phase("configure", True, True, False)
        return True

    def nofetch(self):
        """
        execute the nofetch phase.
        we need the same prerequisites as setup, so reuse that.
        """
        return setup_mixin.setup(self,  "nofetch")

    def unpack(self):
        """
        execute the unpack phase.
        """
        if self.setup_is_for_src:
            self.setup_distfiles()
        if self.userpriv:
            try:
                os.chown(self.env["WORKDIR"], portage_uid, -1)
            except OSError, oe:
                raise format.GenericBuildError(
                    "failed forcing %i uid for WORKDIR: %s" %
                        (portage_uid, str(oe)))
        return self._generic_phase("unpack", True, True, False)

    compile = pretty_docs(
        observer.decorate_build_method("compile")(
            post_curry(
            ebd._generic_phase, "compile", True, True, False)),
            "run the compile phase (maps to src_compile)")

    @observer.decorate_build_method("install")
    @_reset_env_data_source
    def install(self):
        """run the install phase (maps to src_install)"""
        if self.fakeroot:
            return self._generic_phase("install", True, False, True)
        else:
            return self._generic_phase("install", False, True, False)

    @observer.decorate_build_method("test")
    @_reset_env_data_source
    def test(self):
        """run the test phase (if enabled), maps to src_test"""
        if not self.run_test:
            return True
        return self._generic_phase("test", True, True, False)

    def finalize(self):
        """
        finalize the operation.

        this yields a built package, but the packages
        metadata/contents are bound to the workdir. In other words,
        install the package somewhere prior to executing clean if you
        intend on installing it.

        @return: L{pkgcore.ebuild.ebuild_built.package} instance
        """
        return fake_package_factory(self._built_class).new_package(self.pkg,
            self.env["IMAGE"], pjoin(self.env["T"], "environment"))


class binpkg_buildable(ebd, setup_mixin, format.build):

    stage_depends = {"finalize":"setup", "setup":"start"}
    setup_is_for_src = False

    def __init__(self, *args, **kwargs):
        ebd.__init__(self, *args, **kwargs)

    def finalize(self):
        return MutatedPkg(self.pkg, {"environment":self.get_env_source()})
