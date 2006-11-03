#!/usr/bin/env python

import glob
import os
import sys
import errno
import unittest

from distutils import core, ccompiler, log, sysconfig
from distutils.command import build, sdist, build_py, build_scripts, install
from stat import ST_MODE


class mysdist(sdist.sdist):

    """sdist command specifying the right files and generating ChangeLog."""

    default_format = dict(sdist.sdist.default_format)
    default_format["posix"] = "bztar"

    def get_file_list(self):
        for key, globs in self.distribution.package_data.iteritems():
            for pattern in globs:
                self.filelist.extend(glob.glob(os.path.join(key, pattern)))
        self.filelist.append("ChangeLog")
        self.filelist.append("AUTHORS")
        self.filelist.extend(glob.glob('doc/*.rst'))
        self.filelist.extend(glob.glob('dev-notes/*.rst'))
        self.filelist.extend(glob.glob('dev-notes/reimplementation/*.rst'))
        self.filelist.extend(glob.glob('dev-notes/framework/*.rst'))
        self.filelist.append('build_docs.py')
        self.filelist.append(glob.glob('bin/*'))
        self.filelist.exclude_pattern("pkgcore/bin/ebuild-env/filter-env")
        # XXX HACK: if you run "setup.py sdist" with python 2.5 this
        # does not get packaged without this.
        self.filelist.append('pkgcore/util/_functoolsmodule.c')
        sdist.sdist.get_file_list(self)

    def run(self):
        print "regenning ChangeLog (may take a while)"
        os.system("bzr log --verbose > ChangeLog")
        sdist.sdist.run(self)


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


packages = []

for root, dirs, files in os.walk('pkgcore'):
    if '__init__.py' in files:
        package = root.replace(os.path.sep, '.')
        print 'adding package %r' % (package,)
        packages.append(package)

try:
    os.unlink("MANIFEST")
except OSError, oe:
    if oe.errno != errno.ENOENT:
        raise
    del oe


extra_flags = ['-Wall']

extensions = []
if sys.version_info < (2, 5):
    # Almost unmodified copy from the python 2.5 source.
    extensions.append(core.Extension(
            'pkgcore.util._functools', ['pkgcore/util/_functoolsmodule.c'],
            extra_compile_args=extra_flags))


core.setup(
    name='pkgcore',
    version='0.1.4',
    description='package managing framework',
    url='http://gentooexperimental.org/~ferringb/bzr/pkgcore/',
    packages=packages,
    package_data={
        'pkgcore': [
            'data/*',
            'bin/ebuild-env/*',
            'bin/ebuild-helpers/*',
            'heapdef.h',
            ],
        'src': [
            'filter-env/*.c',
            'filter-env/*.h',
            'bsd-flags/*',
            'tbz2tool.c'
            ],
        },
    ext_modules=[
        core.Extension('pkgcore.util._klass', ['pkgcore/util/_klass.c'],
                       extra_compile_args=extra_flags),
        core.Extension('pkgcore.util._caching', ['pkgcore/util/_caching.c'],
                       extra_compile_args=extra_flags),
        core.Extension('pkgcore.util._lists', ['pkgcore/util/_lists.c'],
                       extra_compile_args=extra_flags),
        core.Extension('pkgcore.ebuild._cpv', ['pkgcore/ebuild/_cpv.c'],
                       extra_compile_args=extra_flags),
        core.Extension('pkgcore.util.osutils._readdir',
                       ['pkgcore/util/osutils/_readdir.c'],
                       extra_compile_args=extra_flags),
        ] + extensions,
    cmdclass={'build_filter_env': build_filter_env,
              'sdist': mysdist,
              'build_py': hacked_build_py,
              'test': test,
              'pkgcore_build_scripts': pkgcore_build_scripts,
              'pkgcore_install_scripts': pkgcore_install_scripts,
              },
    )
