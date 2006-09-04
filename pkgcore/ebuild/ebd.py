# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
EBuild Daemon (ebd), main high level interface to ebuild execution env (ebuild.sh being part of it).

Wraps L{pkgcore.ebuild.processor} functionality into a higher level api, per phase methods for example
"""


import os, errno, shutil, operator
import warnings
from pkgcore.interfaces import build, data_source
from pkgcore.ebuild.processor import \
    request_ebuild_processor, release_ebuild_processor, \
    expected_ebuild_env, chuck_UnhandledCommand
from pkgcore.os_data import portage_gid
from pkgcore.fs.util import ensure_dirs, normpath
from pkgcore.os_data import portage_gid
from pkgcore.spawn import spawn_bash, spawn
from pkgcore.util.currying import post_curry, pretty_docs
from pkgcore.os_data import xargs
from pkgcore.ebuild.const import eapi_capable
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.ebuild.ebuild_built:fake_package_factory,package")


def _reset_env_data_source(method):
    def store_env_data_wrapper(self, *args, **kwds):
        try:
            return method(self, *args, **kwds)
        finally:
            # note that we're *not* return'ing anything ourselves.
            # we want the original val to slide back
            if self.env_data_source is None and "PORT_ENV_FILE" in self.env:
                print "\nfiring env_data_source\n"
                try:
                    fp = self.env["PORT_ENV_FILE"]
                    f = self.env_data.get_fileobj()
                    f.seek(0, 0)
                    f.truncate(0)
                    f.write(open(fp, "r").read())
                    del f, fp
                except (IOError, OSError), oe:
                    if oe.errno != errno.ENOENT:
                        raise

    store_env_data_wrapper.__doc__ = method.__doc__
    return store_env_data_wrapper


class ebd(object):

    def __init__(self, pkg, initial_env=None, env_data_source=None, features=None):
        """
        @param pkg: L{ebuild package instance<pkgcore.ebuild.ebuild_src.package>} instance this env is being setup for
        @param initial_env: initial environment to use for this ebuild
        @param env_data_source: a L{pkgcore.interfaces.data_source} instance to restore the environment from- used for restoring the
        state of an ebuild processing, whether for unmerging, or walking phases during building
        @param features: ebuild features, hold over from portage, will be broken down at some point
        """
        
        if pkg.eapi not in eapi_capable:
            raise TypeError("pkg isn't of a supported eapi!, %i not in %s for %s" % (pkg.eapi, eapi_capable, pkg))

        if initial_env is not None:
            # copy.
            self.env = dict(initial_env)
            for x in ("USE", "ACCEPT_LICENSE"):
                if x in self.env:
                    del self.env[x]
        else:
            self.env = {}

        # temp hack.
        if "PYTHONPATH" in os.environ:
            self.env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        if "PORTAGE_DEBUG" in os.environ:
            self.env["PORTAGE_DEBUG"] = str(int(os.environ["PORTAGE_DEBUG"]))
        
        self.env.setdefault("ROOT", "/")
        self.env_data_source = env_data_source
        if env_data_source is not None and not isinstance(env_data_source, data_source.base):
            raise TypeError("env_data_source must be None, or a pkgcore.data_source.base derivative: %s: %s" % (env_data_source.__class__, env_data_source))

        if features is None:
            features = self.env.get("FEATURES", [])

        self.features = set(x.lower() for x in features)

        if "FEATURES" in self.env:
            del self.env["FEATURES"]

        expected_ebuild_env(pkg, self.env)

        self.env["USE"] = ' '.join(str(x) for x in pkg.use)
        self.env["INHERITED"] = ' '.join(pkg.data.get("_eclasses_", {}))

        self.restrict = pkg.restrict

        for x in ("sandbox", "userpriv", "fakeroot"):
            setattr(self, x, self.feat_or_bool(x) and not (x in self.restrict))
        if self.userpriv and os.getuid() != 0:
            self.userpriv = False

        if "PORT_LOGDIR" in self.env:
            self.logging = os.path.join(self.env["PORT_LOGDIR"], pkg.category, pkg.cpvstr+".log")
            del self.env["PORT_LOGDIR"]
        else:
            self.logging = False

        self.env["XARGS"] = xargs

        self.bashrc = self.env.get("bashrc", [])
        if self.bashrc:
            del self.env["bashrc"]

        self.pkg = pkg
        self.eapi = pkg.eapi
        wipes = [k for k, v in self.env.iteritems() if not isinstance(v, basestring)]
        for k in wipes:
            del self.env[k]
        del wipes, k, v

        build.base.__init__(self)
        self.__init_workdir__()
        self.setup_env_data_source(env_data_source)

    def __init_workdir__(self):
        # don't fool with this, without fooling with setup.
        self.base_tmpdir = self.env.pop("PORTAGE_TMPDIR")
        self.tmpdir = normpath(os.path.join(self.base_tmpdir, "portage"))
        self.env["HOME"] = os.path.join(self.tmpdir, "homedir")

        self.builddir = os.path.join(self.tmpdir, self.env["CATEGORY"], self.env["PF"])
        for x, y in (("T", "temp"), ("WORKDIR", "work"), ("D", "image")):
            self.env[x] = os.path.join(self.builddir, y) +"/"
        self.env["IMAGE"] = self.env["D"]

    def setup_env_data_source(self, env_data_source):
        self.env_data_source = env_data_source
        if env_data_source is not None:
            if self.env_data_source.get_path is not None:
                self.env["PORT_ENV_FILE"] = env_data_source.get_path()
            else:
                if not ensure_dirs(self.env["T"], mode=0770, gid=portage_gid, minimal=True):
                    raise build.FailedDirectory(self.env[k], "%s doesn't fulfill minimum mode %o and gid %i" % (k, 0770, portage_gid))
                fp = os.path.join(self.env["T"], "env_data_source")
                open(fp, "w").write(env_data_source.get_fileobj().read())
                self.env["PORT_ENV_FILE"] = fp
        

    def setup_logging(self):
        if self.logging and not ensure_dirs(os.path.dirname(self.logging), mode=02770, gid=portage_gid):
            raise build.FailedDirectory(os.path.dirname(self.logging), "failed ensuring PORT_LOGDIR as 02770 and %i" % portage_gid)

    def setup_workdir(self):
        # ensure dirs.
        for k, text in (("HOME", "home"), ("T", "temp"), ("WORKDIR", "work"), ("D", "image")):
            if not ensure_dirs(self.env[k], mode=0770, gid=portage_gid, minimal=True):
                raise build.FailedDirectory(self.env[k], "%s doesn't fulfill minimum mode %o and gid %i" % (k, 0770, portage_gid))
            # XXX hack, just 'til pkgcore controls these directories
            if (os.stat(self.env[k]).st_mode & 02000):
                warnings.warn("%s ( %s ) is setgid" % (self.env[k], k))

    @_reset_env_data_source
    def setup(self):
        self.setup_workdir()
        self.setup_distfiles()
        self.setup_logging()
        ebd = request_ebuild_processor(userpriv=False, sandbox=False)
        try:
            ebd.prep_phase("setup", self.env, sandbox=self.sandbox, logging=self.logging)
            ebd.write("start_processing")
            if not ebd.generic_handler(additional_commands={"request_inherit":post_curry(ebd.__class__._inherit, self.eclass_cache),
                "request_profiles":self._request_bashrcs}):
                raise build.GenericBuildError("setup: Failed building (False/0 return from handler)")
        except Exception, e:
            # regardless of what occured, we kill the processor.
            ebd.shutdown_processor()
            release_ebuild_processor(ebd)
            # either we know what it is, or it's a shutdown.  re-raise
            if isinstance(e, (SystemExit, build.GenericBuildError)):
                raise
            # wrap.
            raise build.GenericBuildError("setup: Caught exception while building: " + str(e))

        release_ebuild_processor(ebd)
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
                chuck_UnhandledCommand(ebd, "bashrc request: unable to process bashrc '%s' due to source '%s' due to lacking"+
                    "usable get_*" % (val, source))
            if not ebd.expect("next"):
                chuck_UnhandledCommand(ebd, "bashrc transfer, didn't receive 'next' response.  failure?")
        ebd.write("end_request")

    @_reset_env_data_source
    def _generic_phase(self, phase, userpriv, sandbox, fakeroot, extra_handlers=None):
        """
        @param phase: phase to execute
        @param userpriv: will we drop to L{portage_uid<pkgcore.os_data.portage_uid>} and L{portage_gid<pkgcore.os_data.portage_gid>}
        access for this phase?
        @param sandbox: should this phase be sandboxes?
        @param fakeroot: should the phase be fakeroot'd?  Only really useful for install phase, and is mutually exclusive with sandbox
        """
        ebd = request_ebuild_processor(userpriv=(self.userpriv and userpriv), \
            sandbox=(self.sandbox and sandbox), \
            fakeroot=(self.fakeroot and fakeroot))
        try:
            ebd.prep_phase(phase, self.env, sandbox=self.sandbox, logging=self.logging)
            ebd.write("start_processing")
            if not ebd.generic_handler(additional_commands=extra_handlers):
                raise build.GenericBuildError(phase + ": Failed building (False/0 return from handler)")

        except Exception, e:
            ebd.shutdown_processor()
            release_ebuild_processor(ebd)
            if isinstance(e, (SystemExit, build.GenericBuildError)):
                raise
            raise build.GenericBuildError(phase + ": Caught exception while building: %s" % e)

        release_ebuild_processor(ebd)
        return True

    def clean(self):
        if not os.path.exists(self.builddir):
            return True
        try:
            shutil.rmtree(self.builddir)
        except OSError, oe:
            raise build.GenericBuildError("clean: Caught exception while cleansing: %s" % oe)
        return True

    def feat_or_bool(self, name, extra_env=None):
        if name in self.env:
            v = bool(self.env[name])
            del d[name]
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


class install_op(ebd):
    """
    phase operations and steps for install execution
    """

    preinst = pretty_docs(post_curry(ebd._generic_phase, "preinst", False, False, False), "run the postinst phase")
    postinst = pretty_docs(post_curry(ebd._generic_phase, "postinst", False, False, False), "run the postinst phase")


class uninstall_op(ebd):
    """
    phase operations and steps for uninstall execution
    """
    prerm = pretty_docs(post_curry(ebd._generic_phase, "prerm", False, False, False), "run the prerm phase")
    postrm = pretty_docs(post_curry(ebd._generic_phase, "postrm", False, False, False), "run the postrm phase")


class replace_op(uninstall_op, install_op):
    """
    phase operations and steps for replacing a pkg with another
    """
    pass


class buildable(ebd, build.base):

    """
    build operation
    """
    
    _built_class = package

    # XXX this is unclean- should be handing in strictly what is build env, rather then
    # dumping domain settings as env.
    def __init__(self, pkg, domain_settings, eclass_cache, fetcher):
        
        """
        @param pkg: L{pkgcore.ebuild.ebuild_src.package} instance we'll be building
        @param domain_settings: dict bled down from the domain configuration; basically initial env
        @param eclass_cache: the L{eclass_cache<pkgcore.ebuild.eclass_cache>} we'll be using
        @param fetcher: a L{pkgcore.fetch.base.fetcher} instance to use to access our required files for building
        """
    
        ebd.__init__(self, pkg, initial_env=domain_settings, features=domain_settings["FEATURES"])

        self.env["FILESDIR"] = os.path.join(os.path.dirname(pkg.path), "files")
        self.eclass_cache = eclass_cache
        self.env["ECLASSDIR"] = eclass_cache.eclassdir
        self.env["PORTDIR"] = eclass_cache.portdir
        
        self.fetcher = fetcher

        self.run_test = self.feat_or_bool("test", domain_settings) and not "test" in self.restrict

        # XXX minor hack
        path = self.env["PATH"].split(":")

        for s, default in (("DISTCC", ".distcc"), ("CCACHE", "ccache")):
            b = (self.feat_or_bool(s, domain_settings) and not s in self.restrict)
            setattr(self, s.lower(), b)
            if b:
                # looks weird I realize, but os.path.join("/foor/bar", "/barr/foo") == "/barr/foo"
                # and os.path.join("/foo/bar",".asdf") == "/foo/bar/.asdf"
                if not (s+"_DIR") in self.env:
                    self.env[s+"_DIR"] = os.path.join(self.tmpdir,  default)
#				for x in ("CC", "CXX"):
#					if x in self.env:
#						self.env[x] = "%s %s" % (s.lower(), self.env[x])
#					else:
#						self.env[x] = s.lower()
            else:
                for y in ("_PATH", "_DIR"):
                    if s+y in self.env:
                        del self.env[s+y]
        path = [piece for piece in path if piece]
        self.env["PATH"] = ":".join(path)
        self.fetchables = pkg.fetchables[:]
        self.env["A"] = ' '.join(map(operator.attrgetter("filename"), self.fetchables))

    def setup_distfiles(self):
        if self.files:
            # cvs/svn ebuilds need to die.
            #self.env["PORTAGE_ACTUAL_DISTDIR"] = self.env["DISTDIR"]
            self.env["DISTDIR"] = normpath(os.path.join(self.builddir, "distdir"))+"/"

            try:
                if os.path.exists(self.env["DISTDIR"]):
                    if os.path.isdir(self.env["DISTDIR"]) and not os.path.islink(self.env["DISTDIR"]):
                        shutil.rmtree(self.env["DISTDIR"])
                    else:
                        os.unlink(self.env["DISTDIR"])

            except OSError, oe:
                raise build.FailedDirectory(self.env["DISTDIR"], "failed removing existing file/dir/link at: exception %s" % oe)

            if not ensure_dirs(self.env["DISTDIR"], mode=0770, gid=portage_gid):
                raise build.FailedDirectory(self.env["DISTDIR"], "failed creating distdir symlink directory")

            try:
                for src, dest in [(k, os.path.join(self.env["DISTDIR"], v.filename)) for (k, v) in self.files.items()]:
                    os.symlink(src, dest)

            except OSError, oe:
                raise build.GenericBuildError("Failed symlinking in distfiles for src %s -> %s: %s" % (src, dest, str(oe)))

    def setup(self):
        """
        execute the setup phase, mapping out to pkg_setup in the ebuild
        
        necessarily dirs are created as required, and build env is initialized at this point
        """
        if self.distcc:
            for p in ("", "/lock", "/state"):
                if not ensure_dirs(os.path.join(self.env["DISTCC_DIR"], p), mode=02775, gid=portage_gid):
                    raise build.FailedDirectory(os.path.join(self.env["DISTCC_DIR"], p), "failed creating needed distcc directory")
        if self.ccache:
            # yuck.
            st = None
            try:
                st = os.stat(self.env["CCACHE_DIR"])
            except OSError:
                st = None
                if not ensure_dirs(self.env["CCACHE_DIR"], mode=02775, gid=portage_gid):
                    raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed creation of ccache dir")

                # XXX this is more then mildly stupid.
                st = os.stat(self.env["CCACHE_DIR"])
            if st is None:
                try:
                    if st.gid != portage_gid or (st.st_mode & 02070) != 02070:
                        try:
                            cwd = os.getcwd()
                        except OSError:	cwd = "/"
                        try:
                            # crap.
                            os.chmod(self.env["CCACHE_DIR"], 02775)
                            os.chown(self.env["CCACHE_DIR"], -1, portage_gid)
                            os.chdir(cwd)
                            if 0 != spawn(["chgrp", "-R", str(portage_gid)]):
                                raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed changing ownership for CCACHE_DIR")
                            if 0 != spawn_bash("find . -type d | %s chmod 02775" % xargs):
                                raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed correcting perms for CCACHE_DIR")
                        finally:
                            os.chdir(cwd)
                except OSError:
                    raise build.FailedDirectory(self.env["CCACHE_DIR"], "failed ensuring perms/group owner for CCACHE_DIR")
        return ebd.setup(self)

    def configure(self):
        """
        execute the configure phase- does nothing if the pkg is EAPI=0 (that spec lacks a seperated configure phase)
        """
        if self.eapi > 0:
            return self._generic_phase("configure", True, True, False)
        return True

    unpack = pretty_docs(post_curry(ebd._generic_phase, "unpack", True, True, False), "run the unpack phase (maps to src_unpack)")
    compile = pretty_docs(post_curry(ebd._generic_phase, "compile", True, True, False), "run the compile phase (maps to src_compile)")

    @_reset_env_data_source
    def install(self):
        """run the install phase (maps to src_install)"""
        if self.fakeroot:
            return self._generic_phase("install", True, False, True)
        else:
            return self._generic_phase("install", True, True, False)

    @_reset_env_data_source
    def test(self):
        """run the test phase (if enabled), maps to src_test"""
        if not self.run_test:
            return True
        return self._generic_phase("test", True, True, False)

    def finalize(self):
        """
        finalize the operation; this yields a built package, but the packages metadata/contents are bound to the workdir.
        
        In other words, install the package somewhere prior to executing clean if you intend on installing it
        
        @return: L{pkgcore.ebuild.ebuild_built.package} instance
        """
        return fake_package_factory(self._built_class).new_package(self.pkg,
            self.env["IMAGE"], os.path.join(self.env["T"], "environment"))
