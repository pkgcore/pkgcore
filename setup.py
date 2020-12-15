#!/usr/bin/env python3

import glob
import os
import subprocess
import sys
from distutils import log
from distutils.errors import DistutilsExecError
from distutils.util import byte_compile
from itertools import chain

from setuptools import setup
from snakeoil.dist import distutils_extensions as pkgdist

pkgdist_setup, pkgdist_cmds = pkgdist.setup()

# These offsets control where we install the pkgcore config files and the EBD
# bits relative to the install-data path given to the install subcmd.
DATA_INSTALL_OFFSET = 'share/pkgcore'
CONFIG_INSTALL_OFFSET = os.path.join(DATA_INSTALL_OFFSET, 'config')
LIBDIR_INSTALL_OFFSET = 'lib/pkgcore'
EBD_INSTALL_OFFSET = os.path.join(LIBDIR_INSTALL_OFFSET, 'ebd')


class sdist(pkgdist.sdist):
    """sdist wrapper to bundle generated files for release."""

    def make_release_tree(self, base_dir, files):
        """Generate bash function lists for releases."""
        import shutil

        # generate function lists so they don't need to be created on install
        write_pkgcore_ebd_funclists(root='/', target='ebd/.generated')
        write_pkgcore_ebd_cmdlists(root='/', target='ebd/.generated')
        write_pkgcore_ebd_eapi_libs(root='/', target='ebd/.generated')
        shutil.copytree(
            os.path.join(pkgdist.REPODIR, 'ebd', '.generated'),
            os.path.join(base_dir, 'ebd', '.generated'))

        pkgdist.sdist.make_release_tree(self, base_dir, files)


class install(pkgdist.install):
    """Install wrapper to generate and install pkgcore-related files."""

    def run(self):
        super().run()
        target = self.install_data
        root = self.root or '/'
        if target.startswith(root):
            target = os.path.join('/', os.path.relpath(target, root))
        target = os.path.abspath(target)
        if not self.dry_run:
            # Install module plugincache
            # TODO: move this to pkgdist once plugin support is moved to snakeoil
            with pkgdist.syspath(pkgdist.PACKAGEDIR):
                from pkgcore import plugin, plugins
                log.info('Generating plugin cache')
                path = os.path.join(self.install_purelib, 'pkgcore', 'plugins')
                plugin.initialize_cache(plugins, force=True, cache_dir=path)

            # Install configuration data so pkgcore knows where to find its content,
            # rather than assuming it is running from a tarball/git repo.
            write_pkgcore_lookup_configs(self.install_purelib, target)

            # Generate ebd libs when not running from release tarballs that
            # contain pre-generated files.
            if not os.path.exists(os.path.join(pkgdist.REPODIR, 'man')):
                generated_target = os.path.join(target, EBD_INSTALL_OFFSET, '.generated')
                write_pkgcore_ebd_funclists(root=root, target=generated_target)
                write_pkgcore_ebd_cmdlists(root=root, target=generated_target)
                write_pkgcore_ebd_eapi_libs(root=root, target=generated_target)


def write_pkgcore_ebd_funclists(root, target):
    "Generate bash function lists from ebd implementation for env filtering."""
    ebd_dir = target
    if root != '/':
        ebd_dir = os.path.join(root, target.lstrip('/'))
    os.makedirs(os.path.join(ebd_dir, 'funcs'), exist_ok=True)

    # generate global function list
    path = os.path.join(ebd_dir, 'funcs', 'global')
    log.info(f'writing ebd global function list: {path!r}')
    with open(path, 'w') as f:
        if subprocess.call(
                [os.path.join(pkgdist.REPODIR, 'ebd', 'generate_global_func_list')],
                cwd=ebd_dir, stdout=f):
            raise DistutilsExecError("generating global function list failed")

    # generate EAPI specific function lists
    with pkgdist.syspath(pkgdist.PACKAGEDIR):
        from pkgcore.ebuild.eapi import EAPI
        for eapi_obj in EAPI.known_eapis.values():
            eapi = str(eapi_obj)
            path = os.path.join(ebd_dir, 'funcs', eapi)
            log.info(f'writing EAPI {eapi} function list: {path!r}')
            with open(path, 'w') as f:
                if subprocess.call(
                        [os.path.join(pkgdist.REPODIR, 'ebd', 'generate_eapi_func_list'), eapi],
                        cwd=ebd_dir, stdout=f):
                    raise DistutilsExecError(
                        "generating EAPI %s function list failed" % eapi)


def write_pkgcore_ebd_cmdlists(root, target):
    "Generate bash function lists from ebd implementation for env filtering."""
    ebd_dir = target
    if root != '/':
        ebd_dir = os.path.join(root, target.lstrip('/'))
    os.makedirs(os.path.join(ebd_dir, 'cmds'), exist_ok=True)

    # generate EAPI specific command lists
    with pkgdist.syspath(pkgdist.PACKAGEDIR):
        from pkgcore.ebuild.eapi import EAPI
        for eapi_obj in EAPI.known_eapis.values():
            eapi = str(eapi_obj)
            os.makedirs(os.path.join(ebd_dir, 'cmds', eapi), exist_ok=True)

            path = os.path.join(ebd_dir, 'cmds', eapi, 'banned')
            log.info(f'writing EAPI {eapi} banned command list: {path!r}')
            with open(path, 'w') as f:
                if subprocess.call(
                        [os.path.join(pkgdist.REPODIR, 'ebd', 'generate_eapi_cmd_list'), '-b', eapi],
                        cwd=ebd_dir, stdout=f):
                    raise DistutilsExecError(f'generating EAPI {eapi} banned command list failed')

            path = os.path.join(ebd_dir, 'cmds', eapi, 'deprecated')
            log.info(f'writing EAPI {eapi} deprecated command list: {path!r}')
            with open(path, 'w') as f:
                if subprocess.call(
                        [os.path.join(pkgdist.REPODIR, 'ebd', 'generate_eapi_cmd_list'), '-d', eapi],
                        cwd=ebd_dir, stdout=f):
                    raise DistutilsExecError(f'generating EAPI {eapi} deprecated command list failed')

            path = os.path.join(ebd_dir, 'cmds', eapi, 'internal')
            log.info(f'writing EAPI {eapi} internal command list: {path!r}')
            with open(path, 'w') as f:
                if subprocess.call(
                        [os.path.join(pkgdist.REPODIR, 'ebd', 'generate_eapi_cmd_list'), '-i', eapi],
                        cwd=ebd_dir, stdout=f):
                    raise DistutilsExecError(f'generating EAPI {eapi} internal command list failed')


def write_pkgcore_ebd_eapi_libs(root, target):
    "Generate bash EAPI scope libs for sourcing."""
    ebd_dir = target
    if root != '/':
        ebd_dir = os.path.join(root, target.lstrip('/'))

    script = os.path.join(pkgdist.REPODIR, 'ebd', 'generate_eapi_lib')
    with pkgdist.syspath(pkgdist.PACKAGEDIR):
        from pkgcore.ebuild.eapi import EAPI
        for eapi_obj in EAPI.known_eapis.values():
            eapi = str(eapi_obj)
            os.makedirs(os.path.join(ebd_dir, 'libs', eapi), exist_ok=True)

            # generate global scope lib
            path = os.path.join(ebd_dir, 'libs', eapi, 'global')
            log.info(f'writing global EAPI {eapi} lib: {path!r}')
            with open(path, 'w') as f:
                if subprocess.call([script, eapi], cwd=ebd_dir, stdout=f):
                    raise DistutilsExecError(
                        f"generating global scope EAPI {eapi} lib failed")

            for phase in eapi_obj.phases.values():
                # generate phase scope lib
                path = os.path.join(ebd_dir, 'libs', eapi, phase)
                log.info(f'writing EAPI {eapi} {phase} phase lib: {path!r}')
                with open(path, 'w') as f:
                    if subprocess.call([script, '-s', phase, eapi], cwd=ebd_dir, stdout=f):
                        raise DistutilsExecError(
                            f"generating {phase} phase scope EAPI {eapi} lib failed")


def write_pkgcore_lookup_configs(python_base, install_prefix, injected_bin_path=()):
    """Generate file of install path constants."""
    path = os.path.join(python_base, "pkgcore", "_const.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log.info("writing lookup config to %r" % path)

    with open(path, "w") as f:
        os.chmod(path, 0o644)
        # write more dynamic _const file for wheel installs
        if install_prefix != os.path.abspath(sys.prefix):
            import textwrap
            f.write(textwrap.dedent("""\
                import os.path as osp
                import sys

                from snakeoil import process

                INSTALL_PREFIX = osp.abspath(sys.prefix)
                DATA_PATH = osp.join(INSTALL_PREFIX, {!r})
                CONFIG_PATH = osp.join(INSTALL_PREFIX, {!r})
                LIBDIR_PATH = osp.join(INSTALL_PREFIX, {!r})
                EBD_PATH = osp.join(INSTALL_PREFIX, {!r})
                INJECTED_BIN_PATH = ()
                CP_BINARY = process.find_binary('cp')
            """.format(
                DATA_INSTALL_OFFSET, CONFIG_INSTALL_OFFSET,
                LIBDIR_INSTALL_OFFSET, EBD_INSTALL_OFFSET)))
        else:
            f.write("INSTALL_PREFIX=%r\n" % install_prefix)
            f.write("DATA_PATH=%r\n" %
                    os.path.join(install_prefix, DATA_INSTALL_OFFSET))
            f.write("CONFIG_PATH=%r\n" %
                    os.path.join(install_prefix, CONFIG_INSTALL_OFFSET))
            f.write("LIBDIR_PATH=%r\n" %
                    os.path.join(install_prefix, LIBDIR_INSTALL_OFFSET))
            f.write("EBD_PATH=%r\n" %
                    os.path.join(install_prefix, EBD_INSTALL_OFFSET))

            # This is added to suppress the default behaviour of looking
            # within the repo for a bin subdir.
            f.write("INJECTED_BIN_PATH=%r\n" % (tuple(injected_bin_path),))

            # Static paths for various utilities.
            from snakeoil import process
            required_progs = ('cp',)
            try:
                for prog in required_progs:
                    prog_path = process.find_binary(prog)
                    f.write("%s_BINARY=%r\n" % (prog.upper(), prog_path))
            except process.CommandNotFound:
                raise DistutilsExecError(
                    "generating lookup config failed: required utility %r missing from PATH" % (prog,))

            f.close()
            byte_compile([path], prefix=python_base)
            byte_compile([path], optimize=1, prefix=python_base)
            byte_compile([path], optimize=2, prefix=python_base)


class test(pkgdist.pytest):
    """test wrapper to enforce testing against built version."""

    def run(self):
        # This is fairly hacky, but is done to ensure that the tests
        # are ran purely from what's in build, reflecting back to the source
        # only for misc bash scripts or config data.
        key = 'PKGCORE_OVERRIDE_REPO_PATH'
        original = os.environ.get(key)
        try:
            os.environ[key] = os.path.dirname(os.path.realpath(__file__))
            super().run()
        finally:
            if original is not None:
                os.environ[key] = original
            else:
                os.environ.pop(key, None)


setup(**dict(
    pkgdist_setup,
    description='package managing framework',
    url='https://github.com/pkgcore/pkgcore',
    license='BSD',
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    data_files=list(chain(
        pkgdist.data_mapping(EBD_INSTALL_OFFSET, 'ebd'),
        pkgdist.data_mapping(DATA_INSTALL_OFFSET, 'data'),
        pkgdist.data_mapping('share/zsh/site-functions', 'shell/zsh/completion'),
        pkgdist.data_mapping(
            os.path.join(LIBDIR_INSTALL_OFFSET, 'shell'), 'shell',
            skip=glob.glob('shell/*/completion'),
        ),
    )),
    cmdclass=dict(
        pkgdist_cmds,
        sdist=sdist,
        test=test,
        install=install,
    ),
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
))
