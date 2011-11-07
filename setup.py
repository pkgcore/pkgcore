#!/usr/bin/env python

import os
import sys
import subprocess

from distutils import core, log, errors
from distutils.command import (build,
    build_scripts, install)
from stat import ST_MODE

from snakeoil import distutils_extensions as snk_distutils

class mysdist(snk_distutils.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    user_options = snk_distutils.sdist.user_options + [
        ('build-docs', None, 'build docs [default]'),
        ('no-build-docs', None, 'do not build docs'),
        ]

    boolean_options = snk_distutils.sdist.boolean_options + ['build-docs']
    package_namespace = 'pkgcore'

    negative_opt = snk_distutils.sdist.negative_opt.copy()
    negative_opt.update({'no-build-docs':'build-docs'})


    def initialize_options(self):
        snk_distutils.sdist.initialize_options(self)
        self.build_docs = True

    def _add_to_file_list(self):
        self.filelist.include_pattern('doc/*')
        self.filelist.include_pattern('doc/doc/*')
        self.filelist.include_pattern('doc/dev-notes/*')
        self.filelist.include_pattern('man/*')
        self.filelist.append('build_api_docs.sh')
        self.filelist.exclude_pattern("doc/_build")
        self.filelist.exclude_pattern("build")
        self.filelist.include_pattern('examples/*')
        self.filelist.include_pattern('bin/*')

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """
        if self.build_docs:
            # this is icky, but covers up cwd changing issues.
            cwd = os.getcwd()
            if subprocess.call(['python', 'setup.py', 'build_docs', '--builder=man'], cwd=cwd):
                raise errors.DistutilsExecError("build_docs failed")
            import shutil
            shutil.copytree(os.path.join(cwd, "build/sphinx/man"),
                os.path.join(base_dir, "man"))
        snk_distutils.sdist.make_release_tree(self, base_dir, files)
        self.cleanup_post_release_tree(base_dir)


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
                except EnvironmentError:
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

    man_search_path = ('build/sphinx/man', 'man')

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

    def scan_man_pages(self, path=None, first_run=True):
        if path is None:
            cwd = os.getcwd()
            for possible_path in self.man_search_path:
                possible_path = os.path.join(cwd, possible_path)
                if os.path.isdir(possible_path):
                    path = possible_path
                    break
            else:
                if not first_run:
                    if not BuildDoc:
                        raise errors.DistutilsExecError(
                            "no pregenerated man pages, and sphinx isn't available "
                            "to generate them; bailing")
                    raise errors.DistutilsExecError("no man pages found")
                try:
                    self.distribution.get_command_obj('build_man')
                except errors.DistutilsModuleError:
                    # command doesn't exist
                    self.warn("build_man command doesn't exist; sphinx isn't installed, skipping man pages")
                    return []
                self.run_command('build_man')
                return self.scan_man_pages(path=path, first_run=False)
        obj = self.man_pages = [
            os.path.join(path, x) for x in os.listdir(path)
            if len(x) > 2 and x[-2] == '.' and x[-1].isdigit()]
        return obj

    def run(self):
        pages = self.scan_man_pages()
        for x in sorted(set(page[-1] for page in pages)):
            self.mkpath(os.path.join(self.install_man, 'man%s' % x))

        for page in pages:
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
    # this is to disable the older snakeoil machinery that generated bzr versions...
    # we don't use it, primarily.
    generate_bzr_ver = False

    def _recursive_chmod_files(self, base):
        for f in os.listdir(base):
            fp = os.path.join(base, f)
            if os.path.isdir(fp):
                self._recursive_chmod_files(fp)
            elif os.path.isfile(fp):
                self.set_chmod(fp)

    def _inner_run(self, py3k_rebuilds):
        base = os.path.join(self.build_lib, "pkgcore", "ebuild", "eapi-bash")
        self._recursive_chmod_files(os.path.join(base, "helpers"))
        self.set_chmod(os.path.join(base, "ebuild-daemon.bash"))
        self.set_chmod(os.path.join(base, "regenerate_dont_export_func_list.bash"))
        self.set_chmod(os.path.join(base, "filter-env"))
        self.set_chmod(os.path.join(base, "pinspect"))

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
            'pkgcore.restrictions._restrictions', ['src/restrictions.c']),
    ])
    if float(sys.version[:3]) >= 2.6:
        extensions.append(snk_distutils.OptionalExtension(
                'pkgcore.ebuild._misc', ['src/misc.c']))

name = 'pkgcore'
from pkgcore.const import VERSION as version

cmdclass={
    'sdist': mysdist,
    'build_py': pkgcore_build_py,
    'build_ext': snk_distutils.build_ext,
    'test': test,
    'pkgcore_build_scripts': pkgcore_build_scripts,
    'pkgcore_install_scripts': pkgcore_install_scripts,
    'pkgcore_install_man': pkgcore_install_man,
}
command_options = {}

BuildDoc = snk_distutils.sphinx_build_docs()
if BuildDoc:
    cmdclass['build_docs'] = BuildDoc
    command_options['build_docs'] = {
        'version': ('setup.py', version),
        'source_dir': ('setup.py', 'doc'),
        }
    cmdclass['build_man'] = BuildDoc
    command_options['build_man'] = {
        'version': ('setup.py', version),
        'source_dir': ('setup.py', 'doc'),
        'builder': ('setup.py', 'man'),
        }

core.setup(
    name=name,
    version=version,
    description='package managing framework',
    url='http://pkgcore.googlecode.com/',
    license='GPL-2',
    author='Brian Harring',
    author_email='ferringb@gmail.com',
    packages=packages,
    package_data={
        'pkgcore':
            ['ebuild/eapi-bash/%s' % (x,) for x in
                ['filter-env', 'pinspect', '*.lib', 'eapi/*', '*.bash',
                '*.list']
            ] +
            ['ebuild/eapi-bash/helpers/%s' % (x,) for x in ("internals/*", "common/*", "4/*")
            ],
        },
    ext_modules=extensions, cmdclass=cmdclass, command_options=command_options,
    )
