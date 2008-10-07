#!/usr/bin/env python

import os
import sys
import errno
import subprocess
import unittest

from distutils import core, ccompiler, log, errors
from distutils.command import (build, sdist, build_py, build_ext,
    build_scripts, install)
from stat import ST_MODE


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
        except ebzr.NotBranchError, e:
            log.warn('not a branch (%s) trying to determine tag' % (e,))
            return

        if b.supports_tags():
            tags = b.tags.get_reverse_tag_dict().get(b.last_revision())
            if tags:
                f.write("version_info['tags'] = %r\n" % (tags,))

    finally:
        f.close()

class mysdist(sdist.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    user_options = sdist.sdist.user_options + [
        ('build-docs', None, 'build docs [default]'),
        ('no-build-docs', None, 'do not build docs'),
        ('changelog', None, 'create a ChangeLog [default]'),
        ('changelog-start=', None, 'start rev to dump the changelog from,'
            ' defaults to 1'),
        ('no-changelog', None, 'do not create the ChangeLog file'),
        ]

    boolean_options = sdist.sdist.boolean_options + ['changelog'] + ['build-docs']

    negative_opt = {'no-changelog': 'changelog', 'no-build-docs':'build-docs'}
    negative_opt.update(sdist.sdist.negative_opt)

    default_format = dict(sdist.sdist.default_format)
    default_format["posix"] = "bztar"

    def initialize_options(self):
        sdist.sdist.initialize_options(self)
        self.changelog = True
        self.changelog_start = None
        self.build_docs = True

    def get_file_list(self):
        """Get a filelist without doing anything involving MANIFEST files."""
        # This is copied from the "Recreate manifest" bit of sdist.
        self.filelist.findall()
        if self.use_defaults:
            self.add_defaults()

        # This bit is roughly equivalent to a MANIFEST.in template file.
        for key, globs in self.distribution.package_data.iteritems():
            for pattern in globs:
                self.filelist.include_pattern(os.path.join(key, pattern))

        self.filelist.append("AUTHORS")
        self.filelist.append("COPYING")
        self.filelist.append("NEWS")

        self.filelist.include_pattern('.[ch]', prefix='src')

        for prefix in ['doc', 'dev-notes', 'man']:
            self.filelist.include_pattern('.rst', prefix=prefix)
            self.filelist.exclude_pattern(os.path.sep + 'index.rst',
                                          prefix=prefix)
        self.filelist.append('build_docs.py')
        self.filelist.append(os.path.join('man', 'manpage.py'))
        self.filelist.include_pattern('*', prefix='examples')
        self.filelist.include_pattern('*', prefix='bin')

        if self.prune:
            self.prune_file_list()

        # This is not optional: remove_duplicates needs sorted input.
        self.filelist.sort()
        self.filelist.remove_duplicates()

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """
        sdist.sdist.make_release_tree(self, base_dir, files)
        if self.build_docs:
            if subprocess.call(['./build_docs.py'], cwd=base_dir):
                raise errors.DistutilsExecError("build_docs failed")
        if self.changelog:
            args = []
            if self.changelog_start:
                args = ['-r', '%s..-1' % self.changelog_start]
            log.info("regenning ChangeLog (may take a while)")
            if subprocess.call(
                ['bzr', 'log', '--verbose'] + args,
                stdout=open(os.path.join(base_dir, 'ChangeLog'), 'w')):
                raise errors.DistutilsExecError('bzr log failed')
        write_bzr_verinfo(os.path.join(base_dir, 'pkgcore', 'bzr_verinfo.py'))
        for base, dirs, files in os.walk(base_dir):
            for x in files:
                if x.endswith(".pyc") or x.endswith(".pyo"):
                    os.unlink(os.path.join(base, x))


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
                mode = ((os.stat(copyname)[ST_MODE]) | 0555) & 07777
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
                except (IOError, OSError), e:
                    if e.errno != errno.EEXIST:
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


class pkgcore_build_ext(build_ext.build_ext):

    def build_extensions(self):
        if self.debug:
            # say it with me kids... distutils sucks!
            for x in ("compiler_so", "compiler", "compiler_cxx"):
                setattr(self.compiler, x,
                    [y for y in getattr(self.compiler, x) if y != '-DNDEBUG'])
        return build_ext.build_ext.build_extensions(self)



class pkgcore_build_py(build_py.build_py):

    def run(self):
        build_py.build_py.run(self)
        bzr_ver = self.get_module_outfile(
            self.build_lib, ('pkgcore',), 'bzr_verinfo')
        if not os.path.exists(bzr_ver):
            try:
                write_bzr_verinfo(bzr_ver)
            except errors.DistutilsExecError:
                # Not fatal, just less useful --version output.
                log.warn('generating bzr_verinfo failed!')
            else:
                self.byte_compile([bzr_ver])

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
            mode = ((os.stat(path)[ST_MODE]) | 0555) & 07777
            log.info("changing mode of %s to %o", path, mode)
            os.chmod(path, mode)



class TestLoader(unittest.TestLoader):

    """Test loader that knows how to recurse packages."""

    def loadTestsFromModule(self, module):
        """Recurses if module is actually a package."""
        paths = getattr(module, '__path__', None)
        tests = [unittest.TestLoader.loadTestsFromModule(self, module)]
        if paths is None:
            # Not a package.
            return tests[0]
        for path in paths:
            for child in os.listdir(path):
                if (child != '__init__.py' and child.endswith('.py') and
                    child.startswith('test')):
                    # Child module.
                    childname = '%s.%s' % (module.__name__, child[:-3])
                else:
                    childpath = os.path.join(path, child)
                    if not os.path.isdir(childpath):
                        continue
                    if not os.path.exists(os.path.join(childpath,
                                                       '__init__.py')):
                        continue
                    # Subpackage.
                    childname = '%s.%s' % (module.__name__, child)
                tests.append(self.loadTestsFromName(childname))
        return self.suiteClass(tests)


testLoader = TestLoader()


class test(core.Command):

    """Run our unit tests in a built copy.

    Based on code from setuptools.
    """

    user_options = []

    def initialize_options(self):
        # Options? What options?
        pass

    def finalize_options(self):
        # Options? What options?
        pass

    def run(self):
        build_ext = self.reinitialize_command('build_ext')
        build_ext.inplace = True
        self.run_command('build_ext')
        # Somewhat hackish: this calls sys.exit.
        unittest.main('pkgcore.test', argv=['setup.py', '-v'], testLoader=testLoader)


packages = [
    root.replace(os.path.sep, '.')
    for root, dirs, files in os.walk('pkgcore')
    if '__init__.py' in files]

extra_flags = ['-Wall']

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
    ext_modules=[
        core.Extension(
            'pkgcore.ebuild._atom', ['src/atom.c'],
            extra_compile_args=extra_flags),
        core.Extension(
            'pkgcore.ebuild._cpv', ['src/cpv.c'],
            extra_compile_args=extra_flags),
        core.Extension(
            'pkgcore.ebuild._depset', ['src/depset.c'],
            extra_compile_args=extra_flags),
        core.Extension(
            'pkgcore.ebuild._filter_env', [
                'src/filter_env.c', 'src/bmh_search.c'],
            extra_compile_args=extra_flags),
        core.Extension(
            'pkgcore.ebuild._misc', ['src/misc.c'],
            extra_compile_args=extra_flags),
        core.Extension(
            'pkgcore.restrictions._restrictions', ['src/restrictions.c'],
            extra_compile_args=extra_flags),
        ],
    cmdclass={
        'sdist': mysdist,
        'build_py': pkgcore_build_py,
        'build_ext': pkgcore_build_ext,
        'test': test,
        'pkgcore_build_scripts': pkgcore_build_scripts,
        'pkgcore_install_scripts': pkgcore_install_scripts,
        'pkgcore_install_man': pkgcore_install_man,
        },
    )
