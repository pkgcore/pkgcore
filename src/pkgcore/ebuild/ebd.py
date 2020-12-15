"""
EBuild Daemon (ebd), main high level interface to ebuild execution env.

Wraps :obj:`pkgcore.ebuild.processor` functionality into a higher level
api, for example per phase methods.
"""

__all__ = (
    "ebd", "setup_mixin", "install_op", "uninstall_op", "replace_op",
    "buildable", "binpkg_localize")

import errno
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from functools import partial
from itertools import chain
from tempfile import TemporaryFile

from snakeoil import data_source, klass
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.contexts import chdir
from snakeoil.currying import post_curry, pretty_docs
from snakeoil.fileutils import touch
from snakeoil.osutils import ensure_dirs, listdir_files, normpath, pjoin
from snakeoil.process.spawn import (is_sandbox_capable, is_userpriv_capable,
                                    spawn, spawn_bash)
from snakeoil.sequences import iflatten_instance, iter_stable_unique

from .. import const
from ..log import logger
from ..operations import format, observer
from ..os_data import portage_gid, portage_uid, xargs
from ..package.mutated import MutatedPkg
from . import ebd_ipc, ebuild_built, errors
from .processor import (ProcessorError, chuck_UnhandledCommand,
                        expected_ebuild_env, inherit_handler,
                        release_ebuild_processor, request_ebuild_processor)


class ebd:

    def __init__(self, pkg, initial_env=None, env_data_source=None,
                 observer=None, clean=True, tmp_offset=None,
                 allow_fetching=False):
        """
        :param pkg:
            :class:`pkgcore.ebuild.ebuild_src.package`
            instance this env is being setup for
        :param initial_env: initial environment to use for this ebuild
        :param env_data_source: a :obj:`snakeoil.data_source.base` instance
            to restore the environment from- used for restoring the
            state of an ebuild processing, whether for unmerging, or
            walking phases during building
        """
        self.allow_fetching = allow_fetching
        self.pkg = pkg
        self.eapi = pkg.eapi

        if not hasattr(self, "observer"):
            self.observer = observer
        if not self.eapi.is_supported:
            raise TypeError(f"package {pkg} uses unsupported EAPI: {str(self.eapi)!r}")

        if initial_env is not None:
            # copy.
            self.env = dict(initial_env)
            for x in ("USE", "ACCEPT_LICENSE"):
                self.env.pop(x, None)
        else:
            self.env = {}

        # Drop all USE_EXPAND variables from the exported environment.
        for u in self.domain.profile.use_expand:
            self.env.pop(u, None)

        # Only export USE_EXPAND variables for the package's enabled USE flags.
        d = defaultdict(list)
        for u in pkg.use:
            m = self.domain.use_expand_re.match(u)
            if m:
                use_expand, value = m.groups()
                d[use_expand.upper()].append(value)
        for k, v in d.items():
            self.env[k] = ' '.join(sorted(v))

        self.bashrc = self.env.pop("bashrc", ())

        # TODO: drop this once we rewrite/remove calling python-based scripts
        # from the bash side
        if "PYTHONPATH" in os.environ:
            self.env["PYTHONPATH"] = os.environ["PYTHONPATH"]

        self.features = set(x.lower() for x in self.domain.features)
        self.env["FEATURES"] = ' '.join(sorted(self.features))
        self.set_path_vars(self.env, self.pkg, self.domain)

        # internally implemented EAPI specific functions to skip when exporting env
        self.env["PKGCORE_EAPI_FUNCS"] = ' '.join(self.eapi.bash_funcs)

        self.env_data_source = env_data_source
        if (env_data_source is not None and
                not isinstance(env_data_source, data_source.base)):
            raise TypeError(
                "env_data_source must be None, or a pkgcore.data_source.base "
                f"derivative: {env_data_source.__class__}: {env_data_source}")

        iuse_effective_regex = f"^({'|'.join(re.escape(x) for x in pkg.iuse_effective)})$"
        self.env["PKGCORE_IUSE_EFFECTIVE"] = iuse_effective_regex.replace("\\.\\*", ".*")

        expected_ebuild_env(pkg, self.env, env_source_override=self.env_data_source)

        self.env["PKGCORE_FINALIZED_RESTRICT"] = ' '.join(str(x) for x in pkg.restrict)

        self.restrict = pkg.restrict

        for x in ("sandbox", "userpriv"):
            setattr(self, x, self.feat_or_bool(x) and not (x in self.restrict))
        if self.userpriv and os.getuid() != 0:
            self.userpriv = False

        if "PORT_LOGDIR" in self.env:
            self.logging = pjoin(
                self.env["PORT_LOGDIR"],
                "%s:%s:%s.log" % (
                    pkg.cpvstr, self.__class__.__name__,
                    time.strftime("%Y%m%d-%H%M%S", time.localtime())))
            del self.env["PORT_LOGDIR"]
        else:
            self.logging = False

        self.env["PKGCORE_PKG_REPO"] = pkg.source_repository
        self.env["XARGS"] = xargs

        # wipe variables listed in ENV_UNSET for supporting EAPIs
        if self.eapi.options.has_env_unset:
            for x in self.env.pop('ENV_UNSET', ()):
                self.env.pop(x, None)

        # wipe any remaining internal settings from the exported env
        wipes = [k for k, v in self.env.items()
                 if not isinstance(v, str)]
        for k in wipes:
            del self.env[k]

        self._set_op_vars(tmp_offset)
        self.clean_at_start = clean
        self.clean_needed = False

        # various IPC command support
        self._ipc_helpers = {
            # bash helpers
            'doins': ebd_ipc.Doins(self),
            'dodoc': ebd_ipc.Dodoc(self),
            'dohtml': ebd_ipc.Dohtml(self),
            'doinfo': ebd_ipc.Doinfo(self),
            'dodir': ebd_ipc.Dodir(self),
            'doexe': ebd_ipc.Doexe(self),
            'dobin': ebd_ipc.Dobin(self),
            'dosbin': ebd_ipc.Dosbin(self),
            'dolib': ebd_ipc.Dolib(self),
            'dolib.so': ebd_ipc.Dolib_so(self),
            'dolib.a': ebd_ipc.Dolib_a(self),
            'doman': ebd_ipc.Doman(self),
            'domo': ebd_ipc.Domo(self),
            'dosym': ebd_ipc.Dosym(self),
            'dohard': ebd_ipc.Dohard(self),
            'keepdir': ebd_ipc.Keepdir(self),

            # bash functions
            'has_version': ebd_ipc.Has_Version(self),
            'best_version': ebd_ipc.Best_Version(self),
            'unpack': ebd_ipc.Unpack(self),
            'eapply': ebd_ipc.Eapply(self),
            'eapply_user': ebd_ipc.Eapply_User(self),
            'docompress': ebd_ipc.Docompress(self),
            'dostrip': ebd_ipc.Dostrip(self),

            # internals
            'filter_env': ebd_ipc.FilterEnv(self),
        }

    def start(self):
        if self.clean_at_start:
            self.clean_needed = True
            if not self.cleanup():
                return False
        self.setup_workdir()
        self._setup_env_data_source()
        self.clean_needed = True
        return True

    @staticmethod
    def set_path_vars(env, pkg, domain):
        # XXX: note this is just EAPI 3 and EAPI 7 compatibility; not full prefix, soon..
        trailing_slash = pkg.eapi.options.trailing_slash
        env['ROOT'] = domain.root.rstrip(os.sep) + trailing_slash
        env['PKGCORE_PREFIX_SUPPORT'] = 'false'
        if pkg.eapi.options.prefix_capable:
            env['EPREFIX'] = domain.prefix.rstrip(os.sep)
            env['EROOT'] = (
                pjoin(env['ROOT'].rstrip(trailing_slash), env['EPREFIX'])
                + trailing_slash)
            env['PKGCORE_PREFIX_SUPPORT'] = 'true'

        if pkg.eapi.options.has_sysroot:
            env['SYSROOT'] = env['ROOT']
            env['ESYSROOT'] = pjoin(env['SYSROOT'], env['EPREFIX'])
            env['BROOT'] = env['EPREFIX']

    def _set_op_vars(self, tmp_offset):
        # don't fool with this, without fooling with setup.
        self.tmpdir = self.domain.pm_tmpdir
        if tmp_offset:
            self.tmpdir = pjoin(self.tmpdir, tmp_offset.strip(os.sep))

        self.builddir = pjoin(self.tmpdir, self.env["CATEGORY"], self.env["PF"])
        for x, y in (("T", "temp"),
                     ("WORKDIR", "work"),
                     ("D", "image"),
                     ("HOME", "homedir")):
            self.env[x] = normpath(pjoin(self.builddir, y))
        self.env["D"] += self.eapi.options.trailing_slash
        self.env["PORTAGE_LOGFILE"] = normpath(pjoin(self.env["T"], "build.log"))

        # XXX: Note that this is just EAPI 3 support, not yet prefix
        # full awareness.
        if self.pkg.eapi.options.prefix_capable:
            self.env["ED"] = normpath(
                pjoin(self.env["D"].rstrip(os.sep), self.env["EPREFIX"])) \
                    + self.eapi.options.trailing_slash

        # temporary install dir correct for all EAPIs
        self.ED = self.env.get('ED', self.env['D'])

    def get_env_source(self):
        with open(pjoin(self.env["T"], "environment"), "rb") as f:
            return data_source.bytes_data_source(f.read())

    def _setup_env_data_source(self):
        if not ensure_dirs(self.env["T"], mode=0o770, gid=portage_gid, minimal=True):
            raise format.FailedDirectory(
                self.env['T'],
                "%s doesn't fulfill minimum mode %o and gid %i" % (
                    self.env['T'], 0o770, portage_gid))

        if self.env_data_source is not None:
            fp = pjoin(self.env["T"], "environment")
            # load data first (might be a local_source), *then* write
            # if it's a src_ebuild being installed, trying to do two steps
            # stomps the local_sources data.
            data = self.env_data_source.bytes_fileobj().read()
            with open(fp, "wb") as f:
                f.write(data)
            del data

    def _set_per_phase_env(self, phase, env):
        self._setup_merge_type(phase, env)

        # add phase specific helper paths to PATH if they exist
        ebuild_phase = self.eapi.phases.get(phase, '')
        if ebuild_phase in self.eapi.helpers:
            path = chain.from_iterable((
                const.PATH_FORCED_PREPEND,
                self.pkg.eapi.helpers.get('global', ()),
                self.eapi.helpers[ebuild_phase],
                os.environ.get('PATH', '').split(os.pathsep),
            ))
            env['PATH'] = os.pathsep.join(path)

    def _setup_merge_type(self, phase, env):
        # only allowed in pkg_ phases.

        if (not self.eapi.phases.get(phase, "").startswith("pkg_") and
                not phase == 'setup-binpkg'):
            return

        # note all pkgs have this attribute
        is_source = getattr(self.pkg, '_is_from_source', True)

        if self.eapi.options.has_merge_type:
            env["MERGE_TYPE"] = (is_source and "source") or "binary"
        else:
            # we still must export this, just via the portage var name w/
            # different values.  if we didn't, spec or not, kernel binpkg
            # merging would be broke.
            env["EMERGE_FROM"] = (is_source and "ebuild") or "binary"

    def setup_logging(self):
        if self.logging and not ensure_dirs(os.path.dirname(self.logging),
                                            mode=0o2770, gid=portage_gid):
            raise format.FailedDirectory(
                os.path.dirname(self.logging),
                "PORT_LOGDIR, desired mode 02770 and gid %i" % portage_gid)

    def setup_workdir(self):
        # ensure dirs.
        for k in ("HOME", "T", "WORKDIR", "D"):
            if not ensure_dirs(self.env[k], mode=0o4770, gid=portage_gid, minimal=True):
                raise format.FailedDirectory(
                    self.env[k],
                    "%s doesn't fulfill minimum mode %o and gid %i" % (k, 0o770, portage_gid))
            # XXX hack, just 'til pkgcore controls these directories
            if (os.stat(self.env[k]).st_mode & 0o2000):
                logger.warning(f"{self.env[k]} ( {k} ) is setgid")

    def _generic_phase(self, phase, userpriv, sandbox, extra_handlers={},
                       failure_allowed=False, suppress_bashrc=False):
        """
        :param phase: phase to execute
        :param userpriv: will we drop to
            :obj:`pkgcore.os_data.portage_uid` and
            :obj:`pkgcore.os_data.portage_gid` access for this phase?
        :param sandbox: should this phase be sandboxed?
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
        self._set_per_phase_env(phase, self.env)
        extra_handlers = extra_handlers.copy()
        extra_handlers.update(self._ipc_helpers)
        if not suppress_bashrc:
            extra_handlers.setdefault("request_bashrcs", self._request_bashrcs)
        return run_generic_phase(
            self.pkg, phase, self.env, userpriv, sandbox,
            extra_handlers=extra_handlers, failure_allowed=failure_allowed,
            logging=self.logging)

    def _request_bashrcs(self, ebd):
        for source in self.domain.get_package_bashrcs(self.pkg):
            if source.path is not None:
                ebd.write(f"path\n{source.path}")
            elif source.get_data is not None:
                raise NotImplementedError
            else:
                chuck_UnhandledCommand(
                    ebd, "bashrc request: unable to process bashrc "
                    f"due to source '{source}' due to lacking usable get_*")
            if not ebd.expect("next"):
                chuck_UnhandledCommand(
                    ebd, "bashrc transfer, didn't receive 'next' response.  "
                    "failure?")
        ebd.write("end_request")

    def set_is_replacing(self, *pkgs):
        if self.eapi.options.exports_replacing:
            self.env['REPLACING_VERSIONS'] = " ".join(pkg.PVR for pkg in pkgs)

    def set_is_being_replaced_by(self, pkg=None):
        if self.eapi.options.exports_replacing and pkg is not None:
            self.env['REPLACED_BY_VERSION'] = pkg.PVR

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
            except EnvironmentError as e:
                # POSIX specifies either ENOTEMPTY or EEXIST for non-empty dir
                # in particular, Solaris uses EEXIST in that case.
                # https://github.com/pkgcore/pkgcore/pull/181
                if e.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise
        except EnvironmentError as e:
            raise format.GenericBuildError(
                f"clean: Caught exception while cleansing: {e}") from e
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
            touch(pjoin(self.builddir, f'.{stage}'))
        except EnvironmentError:
            # we really don't care...
            pass

    def _reload_state(self):
        try:
            self.__set_stage_state__(
                [x[1:] for x in listdir_files(self.builddir) if x.startswith(".")])
        except EnvironmentError as e:
            if e.errno not in (errno.ENOTDIR, errno.ENOENT):
                raise


class setup_mixin:

    setup_is_for_src = True

    def setup(self, setup_phase_override=None):
        self.setup_logging()

        additional_commands = {}
        phase_name = "setup-binpkg"
        if self.setup_is_for_src:
            phase_name = "setup"
        if setup_phase_override is not None:
            phase_name = setup_phase_override

        if self.setup_is_for_src:
            additional_commands["request_inherit"] = partial(inherit_handler, self.eclass_cache)

        return self._generic_phase(
            phase_name, False, True, extra_handlers=additional_commands)


def run_generic_phase(pkg, phase, env, userpriv, sandbox, fd_pipes=None,
                      extra_handlers=None, failure_allowed=False, logging=None, **kwargs):
    """
    :param phase: phase to execute
    :param env: environment mapping for the phase
    :param userpriv: will we drop to
        :obj:`pkgcore.os_data.portage_uid` and
        :obj:`pkgcore.os_data.portage_gid` access for this phase?
    :param sandbox: should this phase be sandboxed?
    :param fd_pipes: use custom file descriptors for ebd instance
    :type fd_pipes: mapping between file descriptors
    :param extra_handlers: extra command handlers
    :type extra_handlers: mapping from string to callable
    :param failure_allowed: allow failure without raising error
    :type failure_allowed: boolean
    :param logging: None or a filepath to log output to
    :return: True when the phase has finished execution
    """

    userpriv = userpriv and is_userpriv_capable()
    sandbox = sandbox and is_sandbox_capable()
    tmpdir = kwargs.get('tmpdir', env.get('T', None))

    if env is None:
        env = expected_ebuild_env(pkg)

    ebd = request_ebuild_processor(userpriv=userpriv, sandbox=sandbox, fd_pipes=fd_pipes)
    # this is a bit of a hack; used until ebd accepts observers that handle
    # the output redirection on its own.  Primary relevance is when
    # stdout/stderr are pointed at a file; we leave buffering on, just
    # force the flush for synchronization.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        if not ebd.run_phase(phase, env, tmpdir=tmpdir, sandbox=sandbox,
                             logging=logging, additional_commands=extra_handlers):
            if not failure_allowed:
                raise format.GenericBuildError(
                    phase + ": Failed building (False/0 return from handler)")
                logger.warning(f"executing phase {phase}: execution failed, ignoring")
    except Exception as e:
        if isinstance(e, ebd_ipc.IpcError):
            # notify bash side of IPC error
            ebd.write(e.ret)
            if isinstance(e, ebd_ipc.IpcInternalError):
                # show main exception cause for internal IPC errors
                ebd.shutdown_processor(force=True)
                raise e.__cause__
        try:
            ebd.shutdown_processor()
        except ProcessorError as pe:
            # catch die errors during shutdown
            e = pe
        release_ebuild_processor(ebd)
        if isinstance(e, ProcessorError):
            # force verbose die output
            e._verbosity = 1
            raise e
        elif isinstance(e, IGNORED_EXCEPTIONS + (format.GenericBuildError,)):
            raise
        raise format.GenericBuildError(
            f"Executing phase {phase}: Caught exception: {e}") from e

    release_ebuild_processor(ebd)
    return True


class install_op(ebd, format.install):
    """Phase operations and steps for install execution."""

    def __init__(self, domain, pkg, observer):
        format.install.__init__(self, domain, pkg, observer)
        ebd.__init__(
            self, pkg, observer=observer, initial_env=self.domain.settings,
            env_data_source=pkg.environment, clean=False)

    preinst = pretty_docs(
        observer.decorate_build_method("preinst")(
            post_curry(ebd._generic_phase, "preinst", False, False)),
        "run the postinst phase")
    postinst = pretty_docs(
        observer.decorate_build_method("postinst")(
            post_curry(ebd._generic_phase, "postinst", False, False)),
        "run the postinst phase")

    def add_triggers(self, domain_op, engine):
        self.new_pkg.add_format_triggers(domain_op, self, engine)


class uninstall_op(ebd, format.uninstall):
    """Phase operations and steps for uninstall execution."""

    def __init__(self, domain, pkg, observer):
        format.uninstall.__init__(self, domain, pkg, observer)
        ebd.__init__(
            self, pkg, observer=observer, initial_env=self.domain.settings,
            env_data_source=pkg.environment, clean=False,
            tmp_offset="unmerge")

    prerm = pretty_docs(
        observer.decorate_build_method("prerm")(
            post_curry(ebd._generic_phase, "prerm", False, False)),
        "run the prerm phase")
    postrm = pretty_docs(
        observer.decorate_build_method("postrm")(
            post_curry(
                ebd._generic_phase, "postrm", False, False,
                failure_allowed=True)),
        "run the postrm phase")

    def add_triggers(self, domain_op, engine):
        self.old_pkg.add_format_triggers(domain_op, self, engine)

    def finish(self):
        self.cleanup()
        return format.uninstall.finish(self)


class replace_op(format.replace):
    """Phase operations and steps for replace execution."""

    install_kls = staticmethod(install_op)
    uninstall_kls = staticmethod(uninstall_op)

    def __init__(self, domain, old_pkg, new_pkg, observer):
        super().__init__(domain, old_pkg, new_pkg, observer)
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
    """Generic build operation."""

    # XXX this is unclean- should be handing in strictly what is build
    # env, rather then dumping domain settings as env.
    def __init__(self, domain, pkg, verified_files, eclass_cache,
                 observer=None, force_test=False, **kwargs):
        """
        :param pkg: :obj:`pkgcore.ebuild.ebuild_src.package` instance we'll be
            building
        :param eclass_cache: the :class:`pkgcore.ebuild.eclass_cache`
            we'll be using
        :param verified_files: mapping of fetchables mapped to their disk location
        """
        self._built_class = ebuild_built.fresh_built_package
        format.build.__init__(self, domain, pkg, verified_files, observer)
        domain_settings = self.domain.settings
        ebd.__init__(self, pkg, initial_env=domain_settings, **kwargs)

        self.env["FILESDIR"] = pjoin(os.path.dirname(pkg.ebuild.path), "files")
        self.eclass_cache = eclass_cache

        self.run_test = force_test or self.feat_or_bool("test", domain_settings)
        self.allow_failed_test = self.feat_or_bool("test-fail-continue", domain_settings)
        if "test" in self.restrict:
            self.run_test = False
        elif not force_test and "test" not in pkg.use:
            if self.run_test:
                logger.warning(f"disabling test for {pkg} due to test use flag being disabled")
            self.run_test = False

        # XXX minor hack
        path = self.env["PATH"].split(os.pathsep)

        for s, default in (("DISTCC", ".distcc"), ("CCACHE", "ccache")):
            b = (self.feat_or_bool(s, domain_settings) and
                 s not in self.restrict)
            setattr(self, s.lower(), b)
            if b:
                # looks weird I realize, but
                # pjoin("/foor/bar", "/barr/foo") == "/barr/foo"
                # and pjoin("/foo/bar", ".asdf") == "/foo/bar/.asdf"
                self.env.setdefault(s + "_DIR", pjoin(self.domain.tmpdir, default))
                # gentoo bug 355283
                libdir = self.env.get("ABI")
                if libdir is not None:
                    libdir = self.env.get(f"LIBDIR_{libdir}")
                    if libdir is not None:
                        libdir = self.env.get(libdir)
                if libdir is None:
                    libdir = "lib"
                path.insert(0, f"/usr/{libdir}/{s.lower()}/bin")
            else:
                for y in ("_PATH", "_DIR"):
                    if s + y in self.env:
                        del self.env[s+y]
        self.env["PATH"] = os.pathsep.join(path)

        # ordering must match appearance order in SRC_URI per PMS
        self.env["A"] = ' '.join(iter_stable_unique(pkg.distfiles))

        if self.eapi.options.has_AA:
            pkg = self.pkg
            while hasattr(pkg, '_raw_pkg'):
                pkg = getattr(pkg, '_raw_pkg')
            self.env["AA"] = ' '.join(set(iflatten_instance(pkg.distfiles)))

        if self.eapi.options.has_KV:
            self.env["KV"] = domain.KV

        if self.eapi.options.has_merge_type:
            self.env["MERGE_TYPE"] = "source"

        if self.eapi.options.has_portdir:
            self.env["PORTDIR"] = pkg.repo.location
            self.env["ECLASSDIR"] = eclass_cache.eclassdir

        if self.setup_is_for_src:
            self._init_distfiles_env()

    def _init_distfiles_env(self):
        # TODO: PORTAGE_ACTUAL_DISTDIR usage by vcs eclasses needs to be killed off
        distdir_write = self.domain.fetcher.get_storage_path()
        if distdir_write is None:
            raise format.GenericBuildError(
                "no usable distdir was found "
                f"for PORTAGE_ACTUAL_DISTDIR from fetcher {self.domain.fetcher}")
        self.env["PORTAGE_ACTUAL_DISTDIR"] = distdir_write
        self.env["DISTDIR"] = normpath(
            pjoin(self.builddir, "distdir"))
        for x in ("PORTAGE_ACTUAL_DISTDIR", "DISTDIR"):
            self.env[x] = os.path.realpath(self.env[x]).rstrip(os.sep) + os.sep

    def _setup_distfiles(self):
        if not self.verified_files and self.allow_fetching:
            ops = self.domain.pkg_operations(self.pkg, observer=self.observer)
            if not ops.fetch():
                raise format.GenericBuildError("failed fetching required distfiles")
            self.verified_files = ops._fetch_op.verified_files

        if self.verified_files:
            try:
                if os.path.exists(self.env["DISTDIR"]):
                    if (os.path.isdir(self.env["DISTDIR"]) and
                            not os.path.islink(self.env["DISTDIR"])):
                        shutil.rmtree(self.env["DISTDIR"])
                    else:
                        os.unlink(self.env["DISTDIR"])

            except EnvironmentError as e:
                raise format.FailedDirectory(
                    self.env["DISTDIR"],
                    f"failed removing existing file/dir/link: {e}") from e

            if not ensure_dirs(self.env["DISTDIR"], mode=0o770, gid=portage_gid):
                raise format.FailedDirectory(
                    self.env["DISTDIR"],
                    "failed creating distdir symlink directory")

            try:
                for src, dest in [
                        (k, pjoin(self.env["DISTDIR"], v.filename))
                        for (k, v) in self.verified_files.items()]:
                    os.symlink(src, dest)

            except EnvironmentError as e:
                raise format.GenericBuildError(
                    f"Failed symlinking in distfiles for src {src} -> {dest}: {e}") from e

    @observer.decorate_build_method("setup")
    def setup(self):
        """Execute the setup phase, mapping out to pkg_setup in the ebuild.

        Necessarily dirs are created as required, and build env is
        initialized at this point.
        """
        if self.distcc:
            for p in ("", "/lock", "/state"):
                if not ensure_dirs(pjoin(self.env["DISTCC_DIR"], p),
                                   mode=0o2775, gid=portage_gid):
                    raise format.FailedDirectory(
                        pjoin(self.env["DISTCC_DIR"], p),
                        "failed creating needed distcc directory")
        if self.ccache:
            # yuck.
            st = None
            try:
                st = os.stat(self.env["CCACHE_DIR"])
            except OSError as e:
                st = None
                if not ensure_dirs(self.env["CCACHE_DIR"], mode=0o2775,
                                   gid=portage_gid):
                    raise format.FailedDirectory(
                        self.env["CCACHE_DIR"],
                        "failed creation of ccache dir") from e

                # XXX this is more then mildly stupid.
                st = os.stat(self.env["CCACHE_DIR"])
            try:
                if st.st_gid != portage_gid or (st.st_mode & 0o2775) != 0o2775:
                    try:
                        cwd = os.getcwd()
                    except OSError:
                        cwd = "/"
                    with chdir(cwd):
                        # crap.
                        os.chmod(self.env["CCACHE_DIR"], 0o2775)
                        os.chown(self.env["CCACHE_DIR"], -1, portage_gid)
                        if 0 != spawn(
                                ["chgrp", "-R", str(portage_gid), self.env["CCACHE_DIR"]]):
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
            except OSError as e:
                raise format.FailedDirectory(
                    self.env["CCACHE_DIR"],
                    "failed ensuring perms/group owner for CCACHE_DIR") from e

        return setup_mixin.setup(self)

    def configure(self):
        """Execute the configure phase.

        Does nothing if the pkg's EAPI is less than 2 (that spec lacks a
        separated configure phase).
        """
        if "configure" in self.eapi.phases:
            return self._generic_phase("configure", True, True)
        return True

    def prepare(self):
        """Execute a source preparation phase.

        does nothing if the pkg's EAPI is less than 2
        """
        ret = True
        if "prepare" in self.eapi.phases:
            ret = self._generic_phase("prepare", True, True)
            if (self.eapi.options.user_patches and
                    not os.path.exists(pjoin(self.env['T'], '.user_patches_applied'))):
                self.observer.error(
                    'eapply_user (or default) must be called in src_prepare()')
                raise format.GenericBuildError('missing eapply_user call')
        return ret

    def nofetch(self):
        """Execute the nofetch phase.

        We need the same prerequisites as setup, so reuse that.
        """
        ensure_dirs(self.env["T"], mode=0o770, gid=portage_gid, minimal=True)
        return setup_mixin.setup(self, "nofetch")

    def unpack(self):
        """Execute the unpack phase."""
        if self.setup_is_for_src:
            self._setup_distfiles()
        if self.userpriv:
            try:
                os.chown(self.env["WORKDIR"], portage_uid, -1)
            except OSError as e:
                raise format.GenericBuildError(
                    "failed forcing %i uid for WORKDIR: %s" %
                    (portage_uid, e)) from e
        return self._generic_phase("unpack", True, True)

    compile = pretty_docs(
        observer.decorate_build_method("compile")(
            post_curry(ebd._generic_phase, "compile", True, True)),
        "Run the compile phase (maps to src_compile).")

    @observer.decorate_build_method("install")
    def install(self):
        """Run the install phase (maps to src_install)."""
        # TODO: replace print() usage with observer
        print(f">>> Install {self.env['PF']} into {self.ED!r} category {self.env['CATEGORY']}")
        ret = self._generic_phase("install", False, True)
        print(f">>> Completed installing {self.env['PF']} into {self.ED!r}")
        return ret

    @observer.decorate_build_method("test")
    def test(self):
        """Run the test phase (if enabled), maps to src_test."""
        if not self.run_test:
            return True
        return self._generic_phase(
            "test", True, True, failure_allowed=self.allow_failed_test)

    def finalize(self):
        """Finalize the operation.

        This yields a built package, but the packages metadata/contents are
        bound to the workdir. In other words, install the package somewhere
        prior to executing clean if you intend on installing it.

        :return: :obj:`pkgcore.ebuild.ebuild_built.package` instance
        """
        factory = ebuild_built.fake_package_factory(self._built_class)
        return factory.new_package(
            self.pkg, self.env["D"], pjoin(self.env["T"], "environment"))


class binpkg_localize(ebd, setup_mixin, format.build):

    stage_depends = {"finalize": "setup", "setup": "start"}
    setup_is_for_src = False

    def __init__(self, domain, pkg, **kwargs):
        self._built_class = ebuild_built.package
        format.build.__init__(self, domain, pkg, {}, observer=kwargs.get("observer", None))
        ebd.__init__(self, pkg, **kwargs)
        if self.eapi.options.has_merge_type:
            self.env["MERGE_TYPE"] = "binpkg"

    def finalize(self):
        return MutatedPkg(self.pkg, {"environment": self.get_env_source()})


class ebuild_operations:

    _checks = []

    def _register_check(checks):
        """Decorator to register sanity checks that will be run."""
        def _wrap_func(func):
            def wrapped(*args, **kwargs):
                return func(*args, **kwargs)
            checks.append(func)
            return wrapped
        return _wrap_func

    def _cmd_implementation_sanity_check(self, domain):
        """Run all defined sanity checks."""
        failures = []
        for check in self._checks:
            result = check(self, self.pkg, domain=domain)
            if result is not None:
                failures.append(result)
        return self.pkg, failures

    @_register_check(_checks)
    def _check_required_use(self, pkg, **kwargs):
        """Perform REQUIRED_USE verification against a set of USE flags.

        Note that this assumes the REQUIRED_USE depset has been evaluated
        against a known set of enabled USE flags and is in collapsed form.
        """
        if pkg.eapi.options.has_required_use:
            failures = tuple(node for node in pkg.required_use if not node.match(pkg.use))
            if failures:
                return errors.RequiredUseError(pkg, failures)

    @_register_check(_checks)
    def _check_pkg_pretend(self, pkg, *, domain, **kwargs):
        """Run pkg_pretend phase."""
        # pkg_pretend is not defined or required
        if 'pretend' not in pkg.mandatory_phases:
            return

        commands = None
        if not pkg.built:
            commands = {
                'request_inherit': partial(inherit_handler, self._eclass_cache),
                'has_version': ebd_ipc.Has_Version(self),
                'best_version': ebd_ipc.Best_Version(self),
            }

        # Use base build tempdir for $T instead of full pkg specific path to
        # avoid having to create/remove directories -- pkg_pretend isn't
        # allowed to write to the filesystem anyway.
        self.env = expected_ebuild_env(pkg)
        self.env["T"] = domain.pm_tmpdir
        ebd.set_path_vars(self.env, pkg, domain)
        # avoid clipping eend() messages
        self.env["PKGCORE_RC_PREFIX"] = '2'

        with TemporaryFile() as f:
            # suppress bash output by default
            fd_pipes = {1: f.fileno(), 2: f.fileno()}
            try:
                run_generic_phase(
                    pkg, "pretend", self.env, tmpdir=None, fd_pipes=fd_pipes,
                    userpriv=True, sandbox=True, extra_handlers=commands)
            except ProcessorError as e:
                f.seek(0)
                output = f.read().decode().strip('\n')
                return errors.PkgPretendError(pkg, output, e)


class src_operations(ebuild_operations, format.build_operations):

    def __init__(self, domain, pkg, eclass_cache, fetcher=None, observer=None):
        format.build_operations.__init__(self, domain, pkg, observer=observer)
        self._fetcher = fetcher
        self._eclass_cache = eclass_cache

    def _cmd_implementation_build(self, observer, verified_files,
                                  clean=False, allow_fetching=False, force_test=False):
        return buildable(
            self.domain, self.pkg, verified_files,
            self._eclass_cache, observer=observer,
            clean=clean, allow_fetching=allow_fetching, force_test=force_test)


class misc_operations(ebd):

    def __init__(self, domain, *args, **kwds):
        self.domain = domain
        super().__init__(*args, **kwds)

    def configure(self, observer=None):
        return self._generic_phase('config', False, True)

    def info(self, observer=None):
        return self._generic_phase('info', True, True)


class built_operations(ebuild_operations, format.operations):

    def __init__(self, domain, pkg, fetcher=None, observer=None, initial_env=None):
        format.operations.__init__(self, domain, pkg, observer=observer)
        self._fetcher = fetcher
        self._initial_env = initial_env
        self._localized_ebd = None

    def _cmd_implementation_localize(self, observer, force=False):
        if not force and getattr(self.pkg, '_is_from_source', False):
            return self.pkg
        self._localized_ebd = op = binpkg_localize(
            self.domain, self.pkg, clean=False,
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
        misc = misc_operations(
            self.domain, self.pkg, env_data_source=self.pkg.environment, clean=True)
        try:
            misc.start()
            misc.configure()
        finally:
            misc.cleanup()
        return True
