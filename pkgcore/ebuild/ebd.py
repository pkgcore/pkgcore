# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
EBuild Daemon (ebd), main high level interface to ebuild execution env
(ebuild.sh being part of it).

Wraps :obj:`pkgcore.ebuild.processor` functionality into a higher level
api, per phase methods for example
"""

__all__ = ("ebd", "setup_mixin", "install_op", "uninstall_op", "replace_op",
    "buildable", "binpkg_localize")

import os, errno, shutil, sys

from snakeoil import data_source
from snakeoil.compatibility import raise_from, IGNORED_EXCEPTIONS
from pkgcore.ebuild.processor import \
    request_ebuild_processor, release_ebuild_processor, \
    expected_ebuild_env, chuck_UnhandledCommand, \
    inherit_handler
from pkgcore.os_data import portage_gid, portage_uid
from pkgcore.spawn import (
    spawn_bash, spawn, is_sandbox_capable, is_fakeroot_capable,
    is_userpriv_capable, spawn_get_output)
from pkgcore.os_data import xargs
from pkgcore.operations import observer, format
from pkgcore.ebuild import ebuild_built
from snakeoil.currying import post_curry, pretty_docs, partial
from snakeoil import klass
from snakeoil.osutils import (ensure_dirs, normpath, join as pjoin,
    listdir_files)

from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil.lists:iflatten_instance',
    "pkgcore.log:logger",
    "pkgcore.package.mutated:MutatedPkg",
    'pkgcore:fetch',
    "time",
)


class ebd(object):

    def __init__(self, pkg, initial_env=None, env_data_source=None,
                 features=None, observer=None, clean=True, tmp_offset=None,
                 use_override=None, allow_fetching=False):
        """
        :param pkg:
            :class:`pkgcore.ebuild.ebuild_src.package`
            instance this env is being setup for
        :param initial_env: initial environment to use for this ebuild
        :param env_data_source: a :obj:`snakeoil.data_source.base` instance
            to restore the environment from- used for restoring the
            state of an ebuild processing, whether for unmerging, or
            walking phases during building
        :param features: ebuild features, hold over from portage,
            will be broken down at some point
        """


        if use_override is not None:
            use = use_override
        else:
            use = pkg.use

        self.allow_fetching = allow_fetching

        if not hasattr(self, "observer"):
            self.observer = observer
        if not pkg.eapi_obj.is_supported:
            raise TypeError(
                "package %s uses an unsupported eapi: %s" % (pkg, pkg.eapi))

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
        # special note... if CTARGET is the same as CHOST, suppress it.
        # certain ebuilds (nano for example) will misbehave w/ it.
        if pkg.ctarget is not None and pkg.ctarget == pkg.chost:
            self.env.pop("CTARGET")

        if "PYTHONPATH" in os.environ:
            self.env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        if "PKGCORE_DEBUG" in os.environ:
            self.env["PKGCORE_DEBUG"] = str(int(os.environ["PKGCORE_DEBUG"]))

        if features is None:
            features = self.env.get("FEATURES", ())

        # XXX: note this is just eapi3 compatibility; not full prefix, soon..
        self.env["ROOT"] = self.domain.root
        self.prefix_mode = pkg.eapi_obj.options.prefix_capable or 'force-prefix' in features
        self.env["PKGCORE_PREFIX_SUPPORT"] = 'false'
        self.prefix = '/'
        if self.prefix_mode:
            self.env['EROOT'] = normpath(self.domain.root)
            self.prefix = self.domain.prefix.lstrip("/")
            eprefix = normpath(pjoin(self.env["EROOT"], self.prefix))
            if eprefix == '/':
                # Set eprefix to '' if it's basically empty; this keeps certain crappy builds
                # (cmake for example) from puking over //usr/blah pathways
                eprefix = ''
            self.env["EPREFIX"] = eprefix
            self.env["PKGCORE_PREFIX_SUPPORT"] = 'true'

        self.env.update(pkg.eapi_obj.get_ebd_env())

        self.env_data_source = env_data_source
        if env_data_source is not None and \
            not isinstance(env_data_source, data_source.base):
            raise TypeError(
                "env_data_source must be None, or a pkgcore.data_source.base "
                "derivative: %s: %s" % (
                    env_data_source.__class__, env_data_source))

        self.features = set(x.lower() for x in features)

        self.env["FEATURES"] = ' '.join(sorted(self.features))

        expected_ebuild_env(pkg, self.env, env_source_override=self.env_data_source)

        self.env["USE"] = ' '.join(str(x) for x in use)
        self.env["SLOT"] = pkg.fullslot
        self.env["PKGCORE_FINALIZED_RESTRICT"] = ' '.join(str(x) for x in pkg.restrict)

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
                "%s:%s:%s.log" % (pkg.cpvstr, self.__class__.__name__,
                    time.strftime("%Y%m%d-%H%M%S", time.localtime())))
            del self.env["PORT_LOGDIR"]
        else:
            self.logging = False

        self.env["XARGS"] = xargs

        self.bashrc = self.env.pop("bashrc", ())

        self.pkg = pkg
        self.eapi = pkg.eapi
        self.eapi_obj = pkg.eapi_obj
        wipes = [k for k, v in self.env.iteritems()
                 if not isinstance(v, basestring)]
        for k in wipes:
            del self.env[k]

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
        self.tmpdir = normpath(self.domain._get_tempspace())
        if tmp_offset:
            self.tmpdir = pjoin(self.tmpdir,
                tmp_offset.strip(os.path.sep))

        self.builddir = pjoin(self.tmpdir, self.env["CATEGORY"],
            self.env["PF"])
        for x, y in (("T", "temp"), ("WORKDIR", "work"), ("D", "image"),
            ("HOME", "homedir")):
            self.env[x] = normpath(pjoin(self.builddir, y))
        self.env["D"] += "/"
        self.env["IMAGE"] = self.env["D"]

        # XXX: note that this is just eapi3 support, not yet prefix
        # full awareness.
        if self.prefix_mode:
            self.env["ED"] = normpath(pjoin(self.env["D"], self.prefix)) + "/"

    def get_env_source(self):
        return data_source.bytes_data_source(
            open(pjoin(self.env["T"], "environment"), "rb").read())

    def setup_env_data_source(self):
        if not ensure_dirs(self.env["T"], mode=0770, gid=portage_gid,
            minimal=True):
            raise format.FailedDirectory(self.env['T'],
                "%s doesn't fulfill minimum mode %o and gid %i" % (
                self.env['T'], 0770, portage_gid))

        if self.env_data_source is not None:
            fp = pjoin(self.env["T"], "environment")
            # load data first (might be a local_source), *then* write
            # if it's a src_ebuild being installed, trying to do two steps
            # stomps the local_sources data.
            data = self.env_data_source.bytes_fileobj().read()
            open(fp, "wb").write(data)
            del data

    def _set_per_phase_env(self, phase, env):
        self._setup_merge_type(phase, env)

    def _setup_merge_type(self, phase, env):
        # only allowed in pkg_ phases.

        if not self.eapi_obj.phases.get(phase, "").startswith("pkg_") \
            and not phase == 'setup-binpkg':
            return

        # note all pkgs have this attribute
        is_source = getattr(self.pkg, '_is_from_source', True)

        if self.eapi_obj.options.has_merge_type:
            env["MERGE_TYPE"] = (is_source and "source") or "binary"
        else:
            # we still must export this, just via the portage var name w/
            # different values.  if we didn't, spec or not, kernel binpkg
            # merging would be broke.
            env["EMERGE_FROM"] = (is_source and "ebuild") or "binary"

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


    def _generic_phase(self, phase, userpriv, sandbox, fakeroot,
                       extra_handlers={}, failure_allowed=False,
                       suppress_bashrc=False):
        """
        :param phase: phase to execute
        :param userpriv: will we drop to
            :obj:`pkgcore.os_data.portage_uid` and
            :obj:`pkgcore.os_data.portage_gid` access for this phase?
        :param sandbox: should this phase be sandboxed?
        :param fakeroot: should the phase be fakeroot'd?  Only really useful
            for install phase, and is mutually exclusive with sandbox
        """
        if phase not in self.pkg.mandatory_phases:
            # TODO(ferringb): Note the preinst hack; this will be removed once dyn_pkg_preinst
            # is dead in full (currently it has a selinux labelling and suidctl ran from there)
            if phase != 'preinst':
                return True
            if 'selinux' not in self.features and 'suidctl' not in self.features:
                return True
        userpriv = self.userpriv and userpriv
        sandbox = self.sandbox and sandbox
        fakeroot = self.fakeroot and fakeroot
        self._set_per_phase_env(phase, self.env)
        extra_handlers = extra_handlers.copy()
        if not suppress_bashrc:
            extra_handlers.setdefault("request_bashrcs", self._request_bashrcs)
        return run_generic_phase(self.pkg, phase, self.env,
            userpriv, sandbox, fakeroot,
            extra_handlers=extra_handlers, failure_allowed=failure_allowed,
            logging=self.logging)

    def _request_bashrcs(self, ebd, a):
        if a is not None:
            chuck_UnhandledCommand(ebd, "bashrc request with arg"+str(a))
        for source in self.domain.get_package_bashrcs(self.pkg):
            if source.path is not None:
                ebd.write("path\n%s" % source.path)
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

    def set_is_replacing(self, *pkgs):
        if self.eapi_obj.options.exports_replacing:
            self.env['REPLACING_VERSIONS'] = " ".join(x.cpvstr for x in pkgs)

    def set_is_being_replaced_by(self, pkg=None):
        if self.eapi_obj.options.exports_replacing and pkg is not None:
            self.env['REPLACED_BY_VERSION'] = pkg.cpvstr

    def cleanup(self, disable_observer=False, force=False):
        if not force:
            if not self.clean_needed:
                return True
        if not os.path.exists(self.builddir):
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
            except EnvironmentError, e:
                if e.errno != errno.ENOTEMPTY:
                    raise
        except EnvironmentError, oe:
            raise_from(format.GenericBuildError(
                "clean: Caught exception while cleansing: %s" % (oe,)))
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

    def __stage_step_callback__(self, stage):
        try:
            open(pjoin(self.builddir, '.%s' % (stage,)), 'w')
        except EnvironmentError:
            # we really don't care...
            pass

    def _reload_state(self):
        try:
            self.__set_stage_state__([x[1:]
                for x in listdir_files(self.builddir) if x.startswith(".")])
        except EnvironmentError, e:
            if e.errno not in (errno.ENOTDIR, errno.ENOENT):
                raise


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

        if self.setup_is_for_src:
            additional_commands["request_inherit"] = partial(inherit_handler,
                self.eclass_cache)

        return self._generic_phase(phase_name, False, True, False,
            extra_handlers=additional_commands)


def run_generic_phase(pkg, phase, env, userpriv, sandbox, fakeroot,
    extra_handlers=None, failure_allowed=False, logging=None):
    """
    :param phase: phase to execute
    :param userpriv: will we drop to
        :obj:`pkgcore.os_data.portage_uid` and
        :obj:`pkgcore.os_data.portage_gid` access for this phase?
    :param sandbox: should this phase be sandboxed?
    :param fakeroot: should the phase be fakeroot'd?  Only really useful
        for install phase, and is mutually exclusive with sandbox
    """
    userpriv = userpriv and is_userpriv_capable()
    sandbox = sandbox and is_sandbox_capable()
    fakeroot = fakeroot and is_fakeroot_capable()

    if env is None:
        env = expected_ebuild_env(pkg)

    ebd = request_ebuild_processor(userpriv=userpriv, sandbox=sandbox,
        fakeroot=fakeroot)
    # this is a bit of a hack; used until ebd accepts observers that handle
    # the output redirection on it's own.  Primary relevance is when
    # stdout/stderr are pointed at a file; we leave buffering on, just
    # force the flush for synchronization.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        if not ebd.run_phase(phase, env, env.get('T'), sandbox=sandbox,
                       logging=logging,
                       additional_commands=extra_handlers):
            if not failure_allowed:
                raise format.GenericBuildError(
                    phase + ": Failed building (False/0 return from handler)")
                logger.warn("executing phase %s: execution failed, ignoring" % (phase,))

    except Exception, e:
        ebd.shutdown_processor()
        release_ebuild_processor(ebd)
        if isinstance(e, IGNORED_EXCEPTIONS + (format.GenericBuildError,)):
            raise
        raise_from(
            format.GenericBuildError("Executing phase %s: Caught exception: "
                "%s" % (phase, e)))

    release_ebuild_processor(ebd)
    return True


class install_op(ebd, format.install):
    """
    phase operations and steps for install execution
    """

    def __init__(self, domain, pkg, observer):
        format.install.__init__(self, domain, pkg, observer)
        ebd.__init__(self, pkg, observer=observer, initial_env=domain.settings,
            env_data_source=pkg.environment, clean=False)

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

    def add_triggers(self, domain_op, engine):
        self.new_pkg.add_format_triggers(domain_op, self, engine)


class uninstall_op(ebd, format.uninstall):
    """
    phase operations and steps for uninstall execution
    """

    def __init__(self, domain, pkg, observer):
        format.uninstall.__init__(self, domain, pkg, observer)
        ebd.__init__(self, pkg, observer=observer, initial_env=domain.settings,
            env_data_source=pkg.environment, clean=False,
            tmp_offset="unmerge")

    prerm = pretty_docs(
        observer.decorate_build_method("prerm")(
            post_curry(
            ebd._generic_phase, "prerm", False, False, False)),
            "run the prerm phase")
    postrm = pretty_docs(
        observer.decorate_build_method("postrm")(
            post_curry(
            ebd._generic_phase, "postrm", False, False, False,
                failure_allowed=True)),
            "run the postrm phase")

    def add_triggers(self, domain_op, engine):
        self.old_pkg.add_format_triggers(domain_op, self, engine)

    def finish(self):
        self.cleanup()
        return format.uninstall.finish(self)


class replace_op(format.replace):

    install_kls = staticmethod(install_op)
    uninstall_kls = staticmethod(uninstall_op)

    def __init__(self, domain, old_pkg, new_pkg, observer):
        format.replace.__init__(self, domain, old_pkg, new_pkg, observer)
        self.install_op = install_op(domain, new_pkg, observer)
        self.install_op.set_is_replacing(old_pkg)
        self.uninstall_op = uninstall_op(domain, old_pkg, observer)
        self.uninstall_op.set_is_being_replaced_by(new_pkg)

    def start(self):
        self.install_op.start()
        self.uninstall_op.start()
        return True

    prerm = klass.alias_method("uninstall_op.prerm")
    postrm = klass.alias_method("uninstall_op.postrm")
    preinst = klass.alias_method("install_op.preinst")
    postinst = klass.alias_method("install_op.postinst")

    def finalize(self):
        ret = self.uninstall_op.finish()
        ret2 = self.install_op.finish()
        return (ret and ret2)

    def add_triggers(self, domain_op, engine):
        self.uninstall_op.add_triggers(domain_op, engine)
        self.install_op.add_triggers(domain_op, engine)


class buildable(ebd, setup_mixin, format.build):

    """
    build operation
    """

    _built_class = ebuild_built.fresh_built_package

    # XXX this is unclean- should be handing in strictly what is build
    # env, rather then dumping domain settings as env.
    def __init__(self, domain, pkg, verified_files, eclass_cache,
        observer=None, **kwargs):

        """
        :param pkg: :obj:`pkgcore.ebuild.ebuild_src.package` instance we'll be
            building
        :param domain_settings: dict bled down from the domain configuration;
            basically initial env
        :param eclass_cache: the :class:`pkgcore.ebuild.eclass_cache`
            we'll be using
        :param files: mapping of fetchables mapped to their disk location
        """

        use = kwargs.get("use_override", pkg.use)
        domain_settings = domain.settings

        format.build.__init__(self, domain, pkg, verified_files, observer)
        ebd.__init__(self, pkg, initial_env=domain_settings,
                     features=domain_settings["FEATURES"], **kwargs)

        self.env["FILESDIR"] = pjoin(os.path.dirname(pkg.ebuild.path), "files")
        self.eclass_cache = eclass_cache
        self.env["ECLASSDIR"] = eclass_cache.eclassdir
        portdir = self.env["PORTDIR"] = eclass_cache.portdir
        if portdir is None:
            del self.env["PORTDIR"]

        self.run_test = self.feat_or_bool("test", domain_settings)
        if "test" in self.restrict:
            self.run_test = False
        elif "test" not in use:
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
                # gentoo bug 355283
                libdir = self.env.get("ABI")
                if libdir is not None:
                    libdir = self.env.get("LIBDIR_%s" % (libdir,))
                    if libdir is not None:
                        libdir = self.env.get(libdir)
                if libdir is None:
                    libdir = "lib"
                path.insert(0, "/usr/%s/%s/bin" % (libdir, s.lower()))
            else:
                for y in ("_PATH", "_DIR"):
                    if s+y in self.env:
                        del self.env[s+y]
        path = [piece for piece in path if piece]
        self.env["PATH"] = ":".join(path)
        self.env["A"] = ' '.join(set(x.filename
            for x in pkg.fetchables))

        if self.eapi_obj.options.has_AA:
            pkg = getattr(self.pkg, '_raw_pkg', self.pkg)
            self.env["AA"] = ' '.join(set(x.filename
                for x in iflatten_instance(pkg.fetchables, fetch.fetchable)))

        if self.eapi_obj.options.has_KV:
            ret = spawn_get_output(['uname', '-r'])
            if ret[0] == 0:
                self.env["KV"] = ret[1][0].strip()

        if self.eapi_obj.options.has_merge_type:
            self.env["MERGE_TYPE"] = "source"

        if self.setup_is_for_src:
            self.init_distfiles_env()

    def init_distfiles_env(self):
        # cvs/svn ebuilds need to die.
        distdir_write = self.domain.fetcher.get_storage_path()
        if distdir_write is None:
            raise format.GenericBuildError("no usable distdir was found "
                "for PORTAGE_ACTUAL_DISTDIR from fetcher %s" % self.domain.fetcher)
        self.env["PORTAGE_ACTUAL_DISTDIR"] = distdir_write
        self.env["DISTDIR"] = normpath(
            pjoin(self.builddir, "distdir"))
        for x in ("PORTAGE_ACTUAL_DISTDIR", "DISTDIR"):
            self.env[x] = os.path.realpath(self.env[x]).rstrip("/") + "/"

    def setup_distfiles(self):
        if not self.verified_files and self.allow_fetching:
            ops = self.domain.pkg_operations(self.pkg,
                observer=self.observer)
            if not ops.fetch():
                raise format.BuildError("failed fetching required distfiles")
            self.verified_files = ops._fetch_op.verified_files

        if self.verified_files:
            try:
                if os.path.exists(self.env["DISTDIR"]):
                    if (os.path.isdir(self.env["DISTDIR"])
                        and not os.path.islink(self.env["DISTDIR"])):
                        shutil.rmtree(self.env["DISTDIR"])
                    else:
                        os.unlink(self.env["DISTDIR"])

            except EnvironmentError, oe:
                raise_from(format.FailedDirectory(
                    self.env["DISTDIR"],
                    "failed removing existing file/dir/link at: exception %s"
                    % oe))

            if not ensure_dirs(self.env["DISTDIR"], mode=0770,
                               gid=portage_gid):
                raise format.FailedDirectory(
                    self.env["DISTDIR"],
                    "failed creating distdir symlink directory")

            try:
                for src, dest in [
                    (k, pjoin(self.env["DISTDIR"], v.filename))
                    for (k, v) in self.verified_files.iteritems()]:
                    os.symlink(src, dest)

            except EnvironmentError, oe:
                raise_from(format.GenericBuildError(
                    "Failed symlinking in distfiles for src %s -> %s: %s" % (
                        src, dest, str(oe))))

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
                    raise_from(format.FailedDirectory(
                        self.env["CCACHE_DIR"],
                        "failed creation of ccache dir"))

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
                raise_from(format.FailedDirectory(
                    self.env["CCACHE_DIR"],
                    "failed ensuring perms/group owner for CCACHE_DIR"))

        return setup_mixin.setup(self)

    def configure(self):
        """
        execute the configure phase.

        does nothing if the pkg's EAPI is less than 2 (that spec lacks a
        seperated configure phase).
        """
        if "configure" in self.eapi_obj.phases:
            return self._generic_phase("configure", True, True, False)
        return True

    def prepare(self):
        """
        execute a source preparation phase

        does nothing if the pkg's EAPI is less than 2
        """
        if "prepare" in self.eapi_obj.phases:
            return self._generic_phase("prepare", True, True, False)
        return True

    def nofetch(self):
        """
        execute the nofetch phase.
        we need the same prerequisites as setup, so reuse that.
        """
        ensure_dirs(self.env["T"], mode=0770, gid=portage_gid, minimal=True)
        return setup_mixin.setup(self, "nofetch")

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
                raise_from(format.GenericBuildError(
                    "failed forcing %i uid for WORKDIR: %s" %
                        (portage_uid, str(oe))))
        return self._generic_phase("unpack", True, True, False)

    compile = pretty_docs(
        observer.decorate_build_method("compile")(
            post_curry(
            ebd._generic_phase, "compile", True, True, False)),
            "run the compile phase (maps to src_compile)")

    @observer.decorate_build_method("install")
    def install(self):
        """run the install phase (maps to src_install)"""
        if self.fakeroot:
            return self._generic_phase("install", True, False, True)
        else:
            return self._generic_phase("install", False, True, False)

    @observer.decorate_build_method("test")
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

        :return: :obj:`pkgcore.ebuild.ebuild_built.package` instance
        """
        factory = ebuild_built.fake_package_factory(self._built_class)
        return factory.new_package(self.pkg,
            self.env["IMAGE"], pjoin(self.env["T"], "environment"))


class binpkg_localize(ebd, setup_mixin, format.build):

    stage_depends = {"finalize":"setup", "setup":"start"}
    setup_is_for_src = False

    _built_class = ebuild_built.package

    def __init__(self, domain, pkg, **kwargs):
        format.build.__init__(self, domain, pkg, {}, observer=kwargs.get("observer",None))
        ebd.__init__(self, pkg, **kwargs)
        if self.eapi_obj.options.has_merge_type:
            self.env["MERGE_TYPE"] = "binpkg"

    def finalize(self):
        return MutatedPkg(self.pkg, {"environment":self.get_env_source()})


class ebuild_mixin(object):

    def _cmd_implementation_sanity_check(self, domain):
        pkg = self.pkg
        eapi = pkg.eapi_obj
        if eapi.options.has_required_use:
            use = pkg.use
            for node in pkg.required_use:
                if not node.match(use):
                    print "REQUIRED_USE requirement weren't met\nFailed to match: %s\nfrom: %s\nfor USE: %s\npkg: %s" % \
                        (node, pkg.required_use, " ".join(use), pkg.cpvstr)
                    return False
        if 'pretend' not in pkg.mandatory_phases:
            return True
        commands = {"request_inherit": partial(inherit_handler, self._eclass_cache)}
        env = expected_ebuild_env(pkg)
        tmpdir = normpath(domain._get_tempspace())
        builddir = pjoin(tmpdir, env["CATEGORY"], env["PF"])
        pkg_tmpdir = normpath(pjoin(builddir, "temp"))
        ensure_dirs(pkg_tmpdir, mode=0770, gid=portage_gid, minimal=True)
        env["ROOT"] = domain.root
        env["T"] = pkg_tmpdir
        try:
            logger.debug("running ebuild pkg_pretend sanity check for %s", pkg.cpvstr)
            start = time.time()
            ret = run_generic_phase(pkg, "pretend", env, True, True, False,
                extra_handlers=commands)
            logger.debug("pkg_pretend sanity check for %s took %2.2f seconds",
                pkg.cpvstr, time.time() - start)
            return ret
        except format.GenericBuildError, e:
            logger.error("pkg_pretend sanity check for %s failed with exception %r"
                % (pkg.cpvstr, e))
            return False


class src_operations(ebuild_mixin, format.build_operations):

    def __init__(self, domain, pkg, eclass_cache, fetcher=None, observer=None, use_override=None):
        format.build_operations.__init__(self, domain, pkg, observer=observer)
        self._fetcher = fetcher
        self._use_override = use_override
        self._eclass_cache = eclass_cache

    def _cmd_implementation_build(self, observer, verified_files, clean=False, format_options=None):
        if format_options is None:
            format_options = {}
        allow_fetching = format_options.get("allow_fetching", False)
        return buildable(self.domain, self.pkg, verified_files,
            self._eclass_cache,
            use_override=self._use_override,
            clean=clean, allow_fetching=allow_fetching)


class misc_operations(ebd):

    def __init__(self, domain, *args, **kwds):
        self.domain = domain
        ebd.__init__(self, *args, **kwds)

    def configure(self, observer=None):
        return self._generic_phase('config', False, True, False)

    def info(self, observer=None):
        return self._generic_phase('info', True, True, False)


class built_operations(ebuild_mixin, format.operations):

    def __init__(self, domain, pkg, fetcher=None, observer=None, initial_env=None):
        format.operations.__init__(self, domain, pkg, observer=observer)
        self._fetcher = fetcher
        self._initial_env = initial_env
        self._localized_ebd = None

    def _cmd_implementation_localize(self, observer, force=False):
        if not force and getattr(self.pkg, '_is_from_source', False):
            return self.pkg
        self._localized_ebd = op = binpkg_localize(self.domain, self.pkg, clean=False,
            initial_env=self._initial_env, env_data_source=self.pkg.environment,
            observer=observer)
        return op.finalize()

    def _cmd_implementation_cleanup(self, observer, force=False):
        if not self._localized_ebd:
            return True
        return self._localized_ebd.cleanup(force=force)

    def _cmd_check_support_configure(self):
        pkg = self.pkg
        if 'config' not in pkg.mandatory_phases:
            return False
        return True

    def _cmd_implementation_configure(self, observer):
        misc = misc_operations(self.domain, self.pkg, env_data_source=self.pkg.environment, clean=True)
        try:
            misc.start()
            misc.configure()
        finally:
            misc.cleanup()
        return True
