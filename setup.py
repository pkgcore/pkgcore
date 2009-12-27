#!/usr/bin/env python

import os
import sys
import errno
import subprocess
import unittest

from distutils import core, ccompiler, log, errors
from distutils.command import (build, build_py, build_ext,
    build_scripts, install)
from stat import ST_MODE

from snakeoil import distutils_extensions as snk_distutils


def write_bzr_verinfo(destination):
    log.info('generating bzr_verinfo')
    f = open(destination, 'w')
    try:
        if subprocess.call(['bzr', 'version-info', '--format=python'],
                           stdout=f):
            raise errors.DistutilsExecError('bzr version-info failed')
        # HACK: insert the current tag, if possible.
        try:
            from bzrlib import branch, errors as ebzr
        except ImportError:
            log.warn('cannot import bzrlib trying to determine tag')
            return

        try:
            b = branch.Branch.open_containing(__file__)[0]
        except ebzr.NotBranchError:
            log.warn('not a branch (%s) trying to determine tag' % (__file__,))
            return

        if b.supports_tags():
            tags = b.tags.get_reverse_tag_dict().get(b.last_revision())
            if tags:
                f.write("version_info['tags'] = %r\n" % (tags,))

    finally:
        f.close()


class mysdist(snk_distutils.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    user_options = snk_distutils.sdist.user_options + [
        ('build-docs', None, 'build docs [default]'),
        ('no-build-docs', None, 'do not build docs'),
        ]

    boolean_options = snk_distutils.sdist.boolean_options + ['build-docs']

    negative_opt = snk_distutils.sdist.negative_opt.copy()
    negative_opt.update({'no-build-docs':'build-docs'})


    def initialize_options(self):
        snk_distutils.sdist.initialize_options(self)
        self.build_docs = True

    def _add_to_file_list(self):
        self.filelist.include_pattern('.rst', prefix='man')
        self.filelist.exclude_pattern(os.path.sep + 'index.rst',
            prefix='man')
        self.filelist.append('man/manpage.py')
        self.filelist.append('build_api_docs.sh')

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """
        snk_distutils.sdist.make_release_tree(self, base_dir, files)
        if self.build_docs:
            # this is icky, but covers up cwd changing issues.
            my_path = map(os.path.abspath, sys.path)
            if subprocess.call(['./build_docs.py'], cwd=base_dir,
                env={"PYTHONPATH":":".join(my_path)}):
                raise errors.DistutilsExecError("build_docs failed")
        self.cleanup_post_release_tree(base_dir)

    def generate_bzr_verinfo(self, base_dir):
        write_bzr_verinfo(os.path.join(base_dir, 'pkgcore', 'bzr_verinfo.py'))


class pkgcore_build_scripts(build_scripts.build_scripts):

    """Build (modify #! line) the pwrapper_installed script."""

    def finalize_options(self):
        build_scripts.build_scripts.finalize_options(self)
        self.scripts = [os.path.join('bin', 'pwrapper_installed')]

# pkgcore_{build,install}_scripts are registered as separate commands
# instead of overriding the default {build,install}_scripts because
# those are only run if the "scripts" arg to setup is not empty.

build.build.sub_commands.append(('pkgcore_build_scripts', None))


class pkgcore_install_scripts(core.Command):

    """Install symlinks to the pwrapper_installed script.

    Adapted from distutils install_scripts.
    """

    user_options = [
        ('install-dir=', 'd', "directory to install scripts to"),
        ('build-dir=','b', "build directory (where to install from)"),
        ('force', 'f', "force installation (overwrite existing files)"),
        ('skip-build', None, "skip the build steps"),
        ]

    boolean_options = ['force', 'skip-build']

    def initialize_options(self):
        self.install_dir = None
        self.force = 0
        self.build_dir = None
        self.skip_build = None

    def finalize_options(self):
        self.set_undefined_options('build', ('build_scripts', 'build_dir'))
        self.set_undefined_options('install',
                                   ('install_scripts', 'install_dir'),
                                   ('force', 'force'),
                                   ('skip_build', 'skip_build'),
                                   )
        self.scripts = [
            path for path in os.listdir('bin')
            if path not in ('pwrapper', 'pwrapper_installed')]

    def run(self):
        if not self.skip_build:
            self.run_command('pkgcore_build_scripts')
        self.mkpath(self.install_dir)
        if os.name == 'posix':
            # Copy the wrapper once.
            copyname = os.path.join(self.install_dir, self.scripts[0])
            self.copy_file(os.path.join(self.build_dir, 'pwrapper_installed'),
                           copyname)
            # Set the executable bits (owner, group, and world).
            if self.dry_run:
                log.info("changing mode of %s", copyname)
            else:
                # note, we use the int here for python3k compatibility.
                # 365 == 0555, 4095 = 0777
                mode = ((os.stat(copyname)[ST_MODE]) | 365) & 4095
                log.info("changing mode of %s to %o", copyname, mode)
                os.chmod(copyname, mode)
            # Use symlinks for the other scripts.
            for script in self.scripts[1:]:
                # We do not use self.copy_file(link='sym') because we
                # want to make a relative link and copy_file requires
                # the "source" to be an actual file.
                dest = os.path.join(self.install_dir, script)
                log.info('symlinking %s to %s', dest, self.scripts[0])
                try:
                    os.symlink(self.scripts[0], dest)
                except (IOError, OSError):
                    # yes, it would be best to examine the exception...
                    # but that makes this script non py3k sourcable
                    if not os.path.exists(dest):
                        raise
                    os.remove(dest)
                    os.symlink(self.scripts[0], dest)
        else:
            # Just copy all the scripts.
            for script in self.scripts:
                self.copy_file(
                    os.path.join(self.build_dir, 'pwrapper_installed'),
                    os.path.join(self.install_dir, script))

    def get_inputs(self):
        return self.scripts

    def get_outputs(self):
        return self.scripts


class pkgcore_install_man(core.Command):

    """Install man pages"""


    def initialize_options(self):
        self.install_man = None
        self.prefix = None
        self.man_pages = []

    def finalize_options(self):
        self.set_undefined_options('install',
                                   ('root', 'install_man'),
                                   ('install_base', 'prefix'),
                                   )
        if not self.install_man:
            self.install_man = '/'
        self.install_man = os.path.join(self.install_man,
            self.prefix.lstrip(os.path.sep), 'share', 'man')
        self.man_pages = [
            os.path.join(os.getcwd(), 'man', path) for path in os.listdir('man')
            if len(path) > 2 and path[-2] == '.' and path[-1].isdigit()]


    def run(self):
        for x in sorted(set(page[-1] for page in self.man_pages)):
            self.mkpath(os.path.join(self.install_man, 'man%s' % x))

        for page in self.man_pages:
            self.copy_file(
                page,
                os.path.join(self.install_man, 'man%s' % page[-1],
                    os.path.basename(page)))

    def get_inputs(self):
        return self.man_pages

    def get_outputs(self):
        return self.man_pages


install.install.sub_commands.append(('pkgcore_install_scripts', None))
install.install.sub_commands.append(('pkgcore_install_man', None))


class pkgcore_build_py(snk_distutils.build_py):

    package_namespace = 'pkgcore'

    def _inner_run(self, py3k_rebuilds):
        fp = os.path.join(self.build_lib, "pkgcore", "bin", "ebuild-helpers")
        for f in os.listdir(fp):
            self.set_chmod(os.path.join(fp, f))
        fp = os.path.join(self.build_lib, "pkgcore", "bin", "ebuild-env")
        for f in ("ebuild.sh", "ebuild-daemon.sh"):
            self.set_chmod(os.path.join(fp, f))

    def set_chmod(self, path):
        if self.dry_run:
            log.info("changing mode of %s", path)
        else:
            # note, we use the int here for python3k compatibility.
            # 365 == 0555, 4095 = 0777
            mode = ((os.stat(path)[ST_MODE]) | 365) & 4095
            log.info("changing mode of %s to %o", path, mode)
            os.chmod(path, mode)


class test(snk_distutils.test):

    default_test_namespace = 'pkgcore.test'


packages = [
    root.replace(os.path.sep, '.')
    for root, dirs, files in os.walk('pkgcore')
    if '__init__.py' in files]

extensions = []
if not snk_distutils.is_py3k:
    extensions.extend([
        snk_distutils.OptionalExtension(
            'pkgcore.ebuild._atom', ['src/atom.c']),
        snk_distutils.OptionalExtension(
            'pkgcore.ebuild._cpv', ['src/cpv.c']),
        snk_distutils.OptionalExtension(
            'pkgcore.ebuild._depset', ['src/depset.c']),
        snk_distutils.OptionalExtension(
            'pkgcore.ebuild._filter_env', [
                'src/filter_env.c', 'src/bmh_search.c']),
        snk_distutils.OptionalExtension(
            'pkgcore.ebuild._misc', ['src/misc.c']),
        snk_distutils.OptionalExtension(
            'pkgcore.restrictions._restrictions', ['src/restrictions.c']),
    ])

from pkgcore.const import VERSION
core.setup(
    name='pkgcore',
    version=VERSION,
    description='package managing framework',
    url='http://www.pkgcore.org/',
    license='GPL-2',
    packages=packages,
    package_data={
        'pkgcore':
            ['bin/ebuild-env/%s' % x for x in
                ['ebuild-daemon.lib', 'ebuild-daemon.sh', 'ebuild-default-functions.sh', 'ebuild.sh',
                'filter-env', 'isolated-functions.sh', 'portageq_emulation']] +
            ['bin/ebuild-env/eapi/*',
            'bin/ebuild-helpers/*',
            ],
        },
    ext_modules=extensions,
    cmdclass={
        'sdist': mysdist,
        'build_py': pkgcore_build_py,
        'build_ext': snk_distutils.build_ext,
        'test': test,
        'pkgcore_build_scripts': pkgcore_build_scripts,
        'pkgcore_install_scripts': pkgcore_install_scripts,
        'pkgcore_install_man': pkgcore_install_man,
        },
    )
