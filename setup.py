#!/usr/bin/env python

import os
import sys
import subprocess
import unittest

from distutils import core, ccompiler, log, errors
from distutils.command import build, sdist, build_py, build_scripts, install
from stat import ST_MODE


class mysdist(sdist.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    user_options = sdist.sdist.user_options + [
        ('changelog', None, 'create a ChangeLog [default]'),
        ('no-changelog', None, 'do not create the ChangeLog file'),
        ]

    boolean_options = sdist.sdist.boolean_options + ['changelog']

    negative_opt = {'no-changelog': 'changelog'}
    negative_opt.update(sdist.sdist.negative_opt)

    default_format = dict(sdist.sdist.default_format)
    default_format["posix"] = "bztar"

    def initialize_options(self):
        sdist.sdist.initialize_options(self)
        self.changelog = True

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
        self.filelist.append("NOTES")
        self.filelist.append("COPYING")

        # src dir
        self.filelist.include_pattern('.[ch]', prefix='src')
        self.filelist.include_pattern(
            '*', prefix=os.path.join('src', 'bsd-flags'))

        # docs, examples
        for prefix in ['doc', 'dev-notes']:
            self.filelist.include_pattern('.rst', prefix=prefix)
            self.filelist.exclude_pattern(os.path.sep + 'index.rst',
                                          prefix=prefix)
        self.filelist.append('build_docs.py')
        self.filelist.include_pattern('*', prefix='examples')

        self.filelist.include_pattern('*', prefix='bin')
        self.filelist.exclude_pattern(os.path.join(
                'pkgcore', 'bin', 'ebuild-env', 'filter-env'))

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
        if self.changelog:
            log.info("regenning ChangeLog (may take a while)")
            if subprocess.call(
                ['bzr', 'log', '--verbose'],
                stdout=open(os.path.join(base_dir, 'ChangeLog'), 'w')):
                raise errors.DistutilsExecError('bzr log failed')
        if subprocess.call(
            ['bzr', 'version-info', '--format=python'],
            stdout=open(os.path.join(
                    base_dir, 'pkgcore', 'bzr_verinfo.py'), 'w')):
            raise errors.DistutilsExecError('bzr version-info failed')


class build_filter_env(core.Command):

    """Build the filter-env utility.

    This rips a bunch of code from the distutils build_clib command.
    """

    user_options = [
        ('debug', 'g', 'compile with debugging information'),
        ('force', 'f', 'compile everything (ignore timestamps)'),
        ('compiler=', 'c', 'specify the compiler type'),
        ]

    boolean_options = ['debug', 'force']

    help_options = [
        ('help-compiler', None,
         'list available compilers', ccompiler.show_compilers),
        ]

    def initialize_options(self):
        """If we had any options we would initialize them here."""
        self.debug = None
        self.force = 0
        self.compiler = None

    def finalize_options(self):
        """If we had any options we would finalize them here."""
        self.set_undefined_options(
            'build',
            ('debug', 'debug'),
            ('force', 'force'),
            ('compiler', 'compiler'))

    def run(self):
        compiler = ccompiler.new_compiler(
            compiler=self.compiler, dry_run=self.dry_run, force=self.force)
        cc = "%s %s" % (os.environ.get("CC", "cc"), os.environ.get("CFLAGS", ""))
        compiler.set_executables(compiler=cc, compiler_so=cc, linker_exe=cc)
        objects = compiler.compile(list(
                os.path.join('src', 'filter-env', name)
                for name in ('main.c', 'bmh_search.c')), debug=self.debug)
        compiler.link(compiler.EXECUTABLE, objects, os.path.join(
                'pkgcore', 'bin', 'ebuild-env', 'filter-env'))

build.build.sub_commands.append(('build_filter_env', None))


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
                os.symlink(self.scripts[0],
                           os.path.join(self.install_dir, script))
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

install.install.sub_commands.append(('pkgcore_install_scripts', None))


class hacked_build_py(build_py.build_py):

    def run(self):
        build_py.build_py.run(self)

        fp = os.path.join(self.build_lib, "pkgcore", "bin", "ebuild-helpers")
        for f in os.listdir(fp):
            self.set_chmod(os.path.join(fp, f))
        fp = os.path.join(self.build_lib, "pkgcore", "bin", "ebuild-env")
        for f in ("ebuild.sh", "ebuild-daemon.sh"):
            self.set_chmod(os.path.join(fp, f))
        if os.path.exists(os.path.join(fp, "filter-env")):
            self.set_chmod(os.path.join(fp, "filter-env"))

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
        self.run_command('build_filter_env')
        # Somewhat hackish: this calls sys.exit.
        unittest.main('pkgcore.test', argv=['setup.py'], testLoader=testLoader)


packages = [
    root.replace(os.path.sep, '.')
    for root, dirs, files in os.walk('pkgcore')
    if '__init__.py' in files]

extra_flags = ['-Wall']
common_includes = ['src/extensions/py24-compatibility.h',
                   'src/extensions/heapdef.h',
                   ]

extensions = []
if sys.version_info < (2, 5):
    # Almost unmodified copy from the python 2.5 source.
    extensions.append(core.Extension(
            'pkgcore.util._functools', ['src/extensions/functoolsmodule.c'],
            extra_compile_args=extra_flags, depends=common_includes))


core.setup(
    name='pkgcore',
    version='0.1.9',
    description='package managing framework',
    url='http://gentooexperimental.org/~ferringb/bzr/pkgcore/',
    packages=packages,
    package_data={
        'pkgcore': [
            'data/*',
            'bin/ebuild-env/*',
            'bin/ebuild-helpers/*',
            ],
        },
    ext_modules=[
        core.Extension(
            'pkgcore.util.osutils._posix', ['src/extensions/posix.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.util._klass', ['src/extensions/klass.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.util._caching', ['src/extensions/caching.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.util._lists', ['src/extensions/lists.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.ebuild._cpv', ['src/extensions/cpv.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.ebuild._atom', ['src/extensions/atom.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.ebuild._depset', ['src/extensions/depset.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        core.Extension(
            'pkgcore.util.osutils._readdir', ['src/extensions/readdir.c'],
            extra_compile_args=extra_flags, depends=common_includes),
        ] + extensions,
    cmdclass={'build_filter_env': build_filter_env,
              'sdist': mysdist,
              'build_py': hacked_build_py,
              'test': test,
              'pkgcore_build_scripts': pkgcore_build_scripts,
              'pkgcore_install_scripts': pkgcore_install_scripts,
              },
    )
