# Copyright: 2015-2016 Tim Harder <radhermit@gmail.com>
# Copyright: 2008-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

"""
A collection of distutils extensions adding things like automatic 2to3
translation, a test runner, and working around broken stdlib extensions CFLAG
passing in distutils.

Specifically, this module is only meant to be imported in setup.py scripts.
"""

import copy
import errno
import inspect
import io
import math
import operator
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap

os.environ["SNAKEOIL_DEMANDLOAD_PROTECTION"] = 'n'
os.environ["SNAKEOIL_DEMANDLOAD_WARN"] = 'n'

from setuptools.command import install as dst_install

from distutils import log
from distutils.core import Command, Extension
from distutils.errors import DistutilsExecError
from distutils.command import (
    sdist as dst_sdist, build_ext as dst_build_ext, build_py as dst_build_py,
    build as dst_build, build_scripts as dst_build_scripts, config as dst_config)

# getting built by readthedocs
READTHEDOCS = os.environ.get('READTHEDOCS', None) == 'True'

# top level repo/tarball directory
TOPDIR = os.path.dirname(os.path.abspath(inspect.stack(0)[1][1]))


def find_project(topdir=TOPDIR):
    """Determine a project's name.

    Based on the assumption that the project is only distributing one main
    module.
    """
    topdir_depth = len(topdir.split('/'))
    modules = []

    # look for a top-level module
    for root, dirs, files in os.walk(topdir):
        # only descend at most one level
        if len(root.split('/')) > topdir_depth + 1:
            continue
        if '__init__.py' in files:
            modules.append(os.path.basename(root))

    if not modules:
        raise ValueError('No project module found')
    elif len(modules) > 1:
        raise ValueError('Multiple project modules found: %s' % (', '.join(modules)))

    return modules[0]


# determine the project we're being imported into
PROJECT = find_project()


def version(project=PROJECT):
    """Determine a project's version.

    Based on the assumption that a project defines __version__ in its main
    module.
    """
    version = None
    try:
        with io.open(os.path.join(TOPDIR, project, '__init__.py'), encoding='utf-8') as f:
            version = re.search(
                r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                f.read(), re.MULTILINE).group(1)
    except IOError as e:
        if e.errno == errno.ENOENT:
            pass
        else:
            raise

    if version is None:
        raise RuntimeError('Cannot find version for project: %s' % (project,))

    return version


def readme(project=PROJECT):
    """Determine a project's long description."""
    for doc in ('README.rst', 'README'):
        try:
            with io.open(os.path.join(TOPDIR, doc), encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise

    return None


def get_file_paths(path):
    """Get list of all file paths under a given path."""
    for root, dirs, files in os.walk(path):
        for f in files:
            yield os.path.join(root, f)[len(path):].lstrip('/')


def data_mapping(host_prefix, path, skip=None):
    """Map repo paths to host paths for installed data files."""
    skip = list(skip) if skip is not None else []
    for root, dirs, files in os.walk(path):
        host_path = os.path.join(host_prefix, root.partition(path)[2].lstrip('/'))
        repo_path = os.path.join(path, root.partition(path)[2].lstrip('/'))
        if repo_path not in skip:
            yield (host_path, [os.path.join(root, x) for x in files
                               if os.path.join(root, x) not in skip])


def pkg_config(*packages, **kw):
    """Translate pkg-config data to compatible Extension parameters.

    Example usage:

    >>> from distutils.extension import Extension
    >>> from pkgdist import pkg_config
    >>>
    >>> ext_kwargs = dict(
    ...     include_dirs=['include'],
    ...     extra_compile_args=['-std=c++11'],
    ... )
    >>> extensions = [
    ...     Extension('foo', ['foo.c']),
    ...     Extension('bar', ['bar.c'], **pkg_config('lcms2')),
    ...     Extension('ext', ['ext.cpp'], **pkg_config(('nss', 'libusb-1.0'), **ext_kwargs)),
    ... ]
    """
    flag_map = {
        '-I': 'include_dirs',
        '-L': 'library_dirs',
        '-l': 'libraries',
    }

    try:
        tokens = subprocess.check_output(
            ['pkg-config', '--libs', '--cflags'] + list(packages)).split()
    except OSError as e:
        sys.stderr.write('running pkg-config failed: {}\n'.format(e.strerror))
        sys.exit(1)

    for token in tokens:
        token = token.decode()
        if token[:2] in flag_map:
            kw.setdefault(flag_map.get(token[:2]), []).append(token[2:])
        else:
            kw.setdefault('extra_compile_args', []).append(token)
    return kw


class OptionalExtension(Extension):
    """Python extension that is optional to build.

    If it's not required to have the exception built, just preferable,
    use this class instead of :py:class:`Extension` since the machinery
    in this module relies on isinstance to identify what absolutely must
    be built vs what would be nice to have built.
    """
    pass


class sdist(dst_sdist.sdist):
    """sdist command wrapper to bundle generated files for release."""

    package_namespace = PROJECT

    def initialize_options(self):
        dst_sdist.sdist.initialize_options(self)

    def generate_verinfo(self, base_dir):
        """Generate project version module.

        This is used by the --version option in interactive programs among
        other things.
        """
        from snakeoil.version import get_git_version
        log.info('generating _verinfo')
        data = get_git_version(base_dir)
        if not data:
            return
        path = os.path.join(base_dir, self.package_namespace, '_verinfo.py')
        with open(path, 'w') as f:
            f.write('version_info=%r' % (data,))

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """

        if 'build_man' in self.distribution.cmdclass:
            build_man = self.reinitialize_command('build_man')
            build_man.ensure_finalized()
            self.run_command('build_man')
            shutil.copytree(os.path.join(os.getcwd(), build_man.content_search_path[0]),
                            os.path.join(base_dir, build_man.content_search_path[1]))

        dst_sdist.sdist.make_release_tree(self, base_dir, files)
        self.generate_verinfo(base_dir)

    def run(self):
        build_ext = self.reinitialize_command('build_ext')
        build_ext.ensure_finalized()

        # generate cython extensions if any exist
        cython = any(
            os.path.splitext(f)[1] == '.pyx' for e in
            build_ext.extensions for f in e.sources)
        if cython:
            from Cython.Build import cythonize
            cythonize(build_ext.extensions)

        dst_sdist.sdist.run(self)


class build_py(dst_build_py.build_py):
    """build_py command wrapper."""

    user_options = dst_build_py.build_py.user_options + \
        [("inplace", "i", "do any source conversions in place")]

    package_namespace = PROJECT
    generate_verinfo = True

    def initialize_options(self):
        dst_build_py.build_py.initialize_options(self)
        self.inplace = False

    def finalize_options(self):
        self.inplace = bool(self.inplace)
        if self.inplace:
            self.build_lib = '.'
        dst_build_py.build_py.finalize_options(self)

    def _run_generate_verinfo(self, rebuilds=None):
        ver_path = self.get_module_outfile(
            self.build_lib, (self.package_namespace,), '_verinfo')
        # this should check mtime...
        if not os.path.exists(ver_path):
            from snakeoil.version import get_git_version
            log.info('generating _verinfo')
            with open(ver_path, 'w') as f:
                f.write("version_info=%r" % (get_git_version('.'),))
            self.byte_compile([ver_path])
            if rebuilds is not None:
                rebuilds.append((ver_path, os.lstat(ver_path).st_mtime))

    def run(self):
        dst_build_py.build_py.run(self)

        if self.generate_verinfo:
            self._run_generate_verinfo()


class build_py2to3(build_py):
    """build_py command wrapper that runs 2to3 for py3 targets."""

    def _compute_rebuilds(self, force=False):
        for base, mod_name, path in self.find_all_modules():
            try:
                new_mtime = math.floor(os.lstat(path).st_mtime)
            except EnvironmentError:
                # ok... wtf distutils?
                continue
            trg_path = os.path.join(self.build_lib, path)
            if force:
                yield trg_path, new_mtime
                continue
            try:
                old_mtime = math.floor(os.lstat(trg_path).st_mtime)
            except EnvironmentError:
                yield trg_path, new_mtime
                continue
            if old_mtime != new_mtime:
                yield trg_path, new_mtime

    def _inner_run(self, rebuilds):
        pass

    def get_py2to3_converter(self, options=None, proc_count=0):
        from lib2to3 import refactor as ref_mod
        from snakeoil.dist import caching_2to3

        if proc_count == 0:
            import multiprocessing
            proc_count = multiprocessing.cpu_count()

        assert proc_count >= 1

        if proc_count > 1 and not caching_2to3.multiprocessing_available:
            proc_count = 1

        refactor_kls = caching_2to3.MultiprocessRefactoringTool

        fixer_names = ref_mod.get_fixers_from_package('lib2to3.fixes')
        f = refactor_kls(fixer_names, options=options).refactor

        def f2(*args, **kwds):
            if caching_2to3.multiprocessing_available:
                kwds['num_processes'] = proc_count
            return f(*args, **kwds)

        return f2

    def run(self):
        py3k_rebuilds = []
        if not self.inplace:
            if is_py3k:
                py3k_rebuilds = list(self._compute_rebuilds(self.force))
            dst_build_py.build_py.run(self)

        if self.generate_verinfo:
            self._run_generate_verinfo(py3k_rebuilds)

        self._inner_run(py3k_rebuilds)

        if not is_py3k:
            return

        converter = self.get_py2to3_converter()
        log.info("starting 2to3 conversion; this may take a while...")
        converter([x[0] for x in py3k_rebuilds], write=True)
        for path, mtime in py3k_rebuilds:
            os.utime(path, (-1, mtime))
        log.info("completed py3k conversions")


class build_py3to2(build_py2to3):
    """build_py command wrapper that runs 3to2 for py2 targets."""

    def run(self):
        py2k_rebuilds = []
        if not self.inplace:
            if not is_py3k:
                py2k_rebuilds = list(self._compute_rebuilds(self.force))
            dst_build_py.build_py.run(self)

        if self.generate_verinfo:
            self._run_generate_verinfo(py2k_rebuilds)

        self._inner_run(py2k_rebuilds)

        if is_py3k:
            return

        from lib3to2.build import run_3to2
        from lib2to3 import refactor

        # assume a few fixes are already handled in the code or aren't needed
        # for py27
        skip_list = (
            'lib3to2.fixes.fix_str', 'lib3to2.fixes.fix_printfunction',
            'lib3to2.fixes.fix_except', 'lib3to2.fixes.fix_with',
        )
        fixer_names = [x for x in refactor.get_fixers_from_package('lib3to2.fixes')
                       if x not in skip_list]

        log.info("starting 3to2 conversion; this may take a while...")
        run_3to2([x[0] for x in py2k_rebuilds], fixer_names=fixer_names)
        for path, mtime in py2k_rebuilds:
            os.utime(path, (-1, mtime))
        log.info("completed py2k conversions")


class build_man(Command):
    """Build man pages.

    Override the module search path before running sphinx. This fixes
    generating man pages for scripts that need to import modules generated via
    2to3 or other conversions instead of straight from the build directory.
    """

    user_options = [
        ("force", "f", "force build as needed"),
    ]
    content_search_path = ('build/sphinx/man', 'man')

    def initialize_options(self):
        self.force = False

    def finalize_options(self):
        self.force = bool(self.force)

    def skip(self):
        # don't rebuild if one of the output dirs exist
        if any(os.path.exists(x) for x in self.content_search_path):
            log.info('%s: docs already built, skipping regeneration...' %
                     (self.__class__.__name__,))
            return True
        return False

    def run(self):
        if self.force or not self.skip():
            # Use a built version for the man page generation process that
            # imports script modules.
            build_py = self.reinitialize_command('build_py')
            build_py.ensure_finalized()
            self.run_command('build_py')
            syspath = sys.path[:]
            sys.path.insert(0, os.path.abspath(build_py.build_lib))

            # generate man page content for scripts we create
            if 'build_scripts' in self.distribution.cmdclass:
                from snakeoil.dist.generate_docs import generate_man
                generate_man(PROJECT, TOPDIR)

            # generate man pages
            build_sphinx = self.reinitialize_command('build_sphinx')
            build_sphinx.builder = 'man'
            build_sphinx.ensure_finalized()
            self.run_command('build_sphinx')
            sys.path = syspath


class build_docs(build_man):
    """Build html docs."""

    user_options = [
        ("force", "f", "force build as needed"),
    ]
    content_search_path = ('build/sphinx/html', 'html')

    def initialize_options(self):
        self.force = False

    def finalize_options(self):
        self.force = bool(self.force)

    def run(self):
        if self.force or not self.skip():
            # generate man pages -- html versions of man pages are provided
            self.run_command('build_man')

            # generate API docs
            from snakeoil.dist.generate_docs import generate_html
            generate_html(PROJECT, TOPDIR)

            # generate html docs -- allow build_sphinx cmd to run again
            build_sphinx = self.reinitialize_command('build_sphinx')
            build_sphinx.builder = 'html'
            build_sphinx.ensure_finalized()
            self.run_command('build_sphinx')


class build_ext(dst_build_ext.build_ext):

    user_options = dst_build_ext.build_ext.user_options + [
        ("build-optional=", "o", "build optional C modules"),
        ("disable-distutils-flag-fixing", None,
         "disable fixing of issue 969718 in python, adding missing -fno-strict-aliasing"),
    ]

    boolean_options = dst_build.build.boolean_options + ["build-optional"]

    def initialize_options(self):
        dst_build_ext.build_ext.initialize_options(self)
        self.build_optional = None
        self.disable_distutils_flag_fixing = False
        self.default_header_install_dir = None

    def finalize_options(self):
        dst_build_ext.build_ext.finalize_options(self)
        if self.build_optional is None and not READTHEDOCS:
            self.build_optional = True
        self.build_optional = bool(self.build_optional)
        if not self.build_optional:
            self.extensions = [ext for ext in self.extensions if not isinstance(ext, OptionalExtension)]

        # add header install dir to the search path
        # (fixes virtualenv builds for consumer extensions)
        self.set_undefined_options(
            'install',
            ('install_headers', 'default_header_install_dir'))
        if self.default_header_install_dir:
            self.default_header_install_dir = os.path.dirname(self.default_header_install_dir)
            for e in self.extensions:
                # include_dirs may actually be shared between multiple extensions
                if self.default_header_install_dir not in e.include_dirs:
                    e.include_dirs.append(self.default_header_install_dir)

    @staticmethod
    def determine_ext_lang(ext_path):
        """Determine file extensions for generated cython extensions."""
        with open(ext_path) as f:
            for line in f:
                line = line.lstrip()
                if not line:
                    continue
                elif line[0] != '#':
                    return None
                line = line[1:].lstrip()
                if line[:10] == 'distutils:':
                    key, _, value = [s.strip() for s in line[10:].partition('=')]
                    if key == 'language':
                        return value
            else:
                return None

    def no_cythonize(self):
        """Determine file paths for generated cython extensions."""
        extensions = copy.deepcopy(self.extensions)
        for extension in extensions:
            sources = []
            for sfile in extension.sources:
                path, ext = os.path.splitext(sfile)
                if ext in ('.pyx', '.py'):
                    lang = build_ext.determine_ext_lang(sfile)
                    if lang == 'c++':
                        ext = '.cpp'
                    else:
                        ext = '.c'
                    sfile = path + ext
                sources.append(sfile)
            extension.sources[:] = sources
        return extensions

    def run(self):
        # ensure that the platform checks were performed
        self.run_command('config')

        # only regenerate cython extensions if requested or required
        use_cython = (
            os.environ.get('USE_CYTHON', False) or
            any(not os.path.exists(x) for ext in self.no_cythonize() for x in ext.sources))
        if use_cython:
            from Cython.Build import cythonize
            cythonize(self.extensions)

        self.extensions = self.no_cythonize()
        return dst_build_ext.build_ext.run(self)

    def build_extensions(self):
        # say it with me kids... distutils sucks!
        for x in ("compiler_so", "compiler", "compiler_cxx"):
            if self.debug:
                l = [y for y in getattr(self.compiler, x) if y != '-DNDEBUG']
                l.append('-Wall')
                setattr(self.compiler, x, l)
            if not self.disable_distutils_flag_fixing:
                val = getattr(self.compiler, x)
                if "-fno-strict-aliasing" not in val:
                    val.append("-fno-strict-aliasing")
            if getattr(self.distribution, 'check_defines', None):
                val = getattr(self.compiler, x)
                for d, result in self.distribution.check_defines.items():
                    if result:
                        val.append('-D%s=1' % d)
                    else:
                        val.append('-U%s' % d)
        return dst_build_ext.build_ext.build_extensions(self)


class build_scripts(dst_build_scripts.build_scripts):
    """Create and build (copy and modify #! line) the wrapper scripts."""

    def finalize_options(self):
        dst_build_scripts.build_scripts.finalize_options(self)
        script_dir = os.path.join(
            os.path.dirname(self.build_dir), '.generated_scripts')
        self.mkpath(script_dir)
        self.scripts = [os.path.join(script_dir, x) for x in os.listdir('bin')]

    def run(self):
        for script in self.scripts:
            with open(script, 'w') as f:
                f.write(textwrap.dedent("""\
                    #!%s
                    from os.path import basename
                    from %s import scripts
                    scripts.main(basename(__file__))
                """ % (sys.executable, PROJECT)))
        self.copy_scripts()


class build(dst_build.build):
    """Generic build command."""

    user_options = dst_build.build.user_options[:]
    user_options.append(('enable-man-pages', None, 'build man pages'))
    user_options.append(('enable-html-docs', None, 'build html docs'))

    boolean_options = dst_build.build.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    sub_commands = dst_build.build.sub_commands[:]
    sub_commands.append(('build_ext', None))
    sub_commands.append(('build_py', None))
    sub_commands.append(('build_scripts', None))
    sub_commands.append(('build_docs', operator.attrgetter('enable_html_docs')))
    sub_commands.append(('build_man', operator.attrgetter('enable_man_pages')))

    def initialize_options(self):
        dst_build.build.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        dst_build.build.finalize_options(self)
        if self.enable_man_pages is None:
            path = os.path.dirname(os.path.abspath(__file__))
            self.enable_man_pages = not os.path.exists(os.path.join(path, 'man'))

        if self.enable_html_docs is None:
            self.enable_html_docs = False


class install_docs(Command):
    """Install html documentation."""

    content_search_path = build_docs.content_search_path
    user_options = [
        ('path=', None, "final path to install to; else it's calculated"),
        ('build-dir=', None, "build directory"),
    ]
    build_command = 'build_docs'

    def initialize_options(self):
        self.root = None
        self.prefix = None
        self.path = None
        self.build_dir = None
        self.content = []
        self.source_path = None

    def finalize_options(self):
        self.set_undefined_options(
            'install',
            ('root', 'root'),
            ('install_base', 'prefix'),
        )
        if not self.root:
            self.root = '/'
        if self.path is None:
            self.path = os.path.join(
                self.root, self.calculate_install_path().lstrip(os.path.sep))

    def calculate_install_path(self):
        return os.path.join(
            os.path.abspath(self.prefix), 'share', 'doc', PROJECT + '-%s' % version(), 'html')

    def find_content(self):
        for possible_path in self.content_search_path:
            if self.build_dir is not None:
                possible_path = os.path.join(self.build_dir, possible_path)
            possible_path = os.path.join(TOPDIR, possible_path)
            if os.path.isdir(possible_path):
                return possible_path
        else:
            return None

    def _map_paths(self, content):
        return {x: x for x in content}

    def scan_content(self):
        self.content = self._map_paths(get_file_paths(self.source_path))
        return self.content

    def run(self, firstrun=True):
        self.source_path = self.find_content()
        if self.source_path is None:
            if not firstrun:
                raise DistutilsExecError(
                    "no pregenerated sphinx content, and sphinx isn't available "
                    "to generate it; bailing")
            self.run_command(self.build_command)
            return self.run(False)

        content = self.scan_content()

        content = self.content
        directories = set(map(os.path.dirname, content.values()))
        directories.discard('')
        for x in sorted(directories):
            self.mkpath(os.path.join(self.path, x))

        for src, dst in sorted(content.items()):
            self.copy_file(
                os.path.join(self.source_path, src),
                os.path.join(self.path, dst))

    def get_inputs(self):
        # Py3k compatibility- force list so behaviour is the same.
        return list(self.content)

    def get_outputs(self):
        # Py3k compatibility- force list so behaviour is the same.
        return list(self.content.values())


class install_man(install_docs):
    """Install man pages."""

    content_search_path = build_man.content_search_path
    build_command = 'build_man'

    def calculate_install_path(self):
        return os.path.join(self.prefix, 'share', 'man')

    def _map_paths(self, content):
        d = {}
        for x in content:
            if len(x) >= 3 and x[-2] == '.' and x[-1].isdigit():
                # Only consider extensions .1, .2, .3, etc, and files that
                # have at least a single char beyond the extension (thus ignore
                # .1, but allow a.1).
                d[x] = 'man%s/%s' % (x[-1], os.path.basename(x))
        return d


class install(dst_install.install):
    """Generic install command."""

    user_options = dst_install.install.user_options[:]
    user_options.append(('enable-man-pages', None, 'install man pages'))
    user_options.append(('enable-html-docs', None, 'install html docs'))

    boolean_options = dst_install.install.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    def initialize_options(self):
        dst_install.install.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        build_options = self.distribution.command_options.setdefault('build', {})
        build_options['enable_html_docs'] = ('command_line', self.enable_html_docs and 1 or 0)
        man_pages = self.enable_man_pages
        if man_pages and os.path.exists('man'):
            man_pages = False
        build_options['enable_man_pages'] = ('command_line', man_pages and 1 or 0)
        dst_install.install.finalize_options(self)

    sub_commands = dst_install.install.sub_commands[:]
    sub_commands.append(('install_man', operator.attrgetter('enable_man_pages')))
    sub_commands.append(('install_docs', operator.attrgetter('enable_html_docs')))


class test(Command):
    """Run our unit tests in a built copy.

    Based on code from setuptools.
    """

    blacklist = frozenset()

    user_options = [
        ("inplace", "i", "do building/testing in place"),
        ("skip-rebuilding", "s", "skip rebuilds. primarily for development"),
        ("disable-fork", None, "disable forking of the testloader; primarily for debugging.  "
                               "Automatically set in jython, disabled for cpython/unladen-swallow."),
        ("namespaces=", "t", "run only tests matching these namespaces.  "
                             "comma delimited"),
        ("pure-python", None, "disable building of extensions.  Enabled for jython, disabled elsewhere"),
        ("force", "f", "force build_py/build_ext as needed"),
        ("include-dirs=", "I", "include dirs for build_ext if needed"),
    ]

    default_test_namespace = '%s.test' % PROJECT

    def initialize_options(self):
        self.inplace = False
        self.disable_fork = is_jython
        self.namespaces = ''
        self.pure_python = is_jython
        self.force = False
        self.include_dirs = None

    def finalize_options(self):
        self.inplace = bool(self.inplace)
        self.disable_fork = bool(self.disable_fork)
        self.pure_python = bool(self.pure_python)
        self.force = bool(self.force)
        if isinstance(self.include_dirs, str):
            self.include_dirs = self.include_dirs.split(os.pathsep)
        if self.namespaces:
            self.namespaces = tuple(set(self.namespaces.split(',')))
        else:
            self.namespaces = ()

    def run(self):
        from snakeoil.dist import unittest_extensions

        build_ext = self.reinitialize_command('build_ext')
        build_py = self.reinitialize_command('build_py')
        build_ext.inplace = build_py.inplace = self.inplace
        build_ext.force = build_py.force = self.force
        build_ext.ensure_finalized()
        build_py.ensure_finalized()

        if self.include_dirs:
            build_ext.include_dirs = self.include_dirs

        if not self.pure_python:
            self.run_command('build_ext')
        if not self.inplace:
            self.run_command('build_py')

        syspath = sys.path[:]
        mods_to_wipe = ()
        if not self.inplace:
            cwd = os.getcwd()
            syspath = [x for x in sys.path if x != cwd]
            test_path = os.path.abspath(build_py.build_lib)
            syspath.insert(0, test_path)
            mods = build_py.find_all_modules()
            mods_to_wipe = set(x[0] for x in mods)
            mods_to_wipe.update('.'.join(x[:2]) for x in mods)

        namespaces = self.namespaces
        if not self.namespaces:
            namespaces = [self.default_test_namespace]

        retval = unittest_extensions.run_tests(
            namespaces, disable_fork=self.disable_fork,
            blacklist=self.blacklist, pythonpath=syspath,
            modules_to_wipe=mods_to_wipe)

        # remove temporary plugincache so it isn't installed
        plugincache = os.path.join(
            os.path.abspath(build_py.build_lib), build_py.package_namespace,
            'plugins/plugincache')
        if os.path.exists(plugincache):
            os.remove(plugincache)

        if retval:
            raise DistutilsExecError("tests failed; return %i" % (retval,))


class PyTest(Command):
    """Run tests using pytest against a built copy."""

    user_options = [
        ('pytest-args=', 'a', 'arguments to pass to py.test'),
        ('coverage', 'c', 'generate coverage info'),
        ('report=', 'r', 'generate and/or show a coverage report'),
        ('jobs=', 'j', 'run X parallel tests at once'),
        ('match=', 'k', 'run only tests that match the provided expressions'),
    ]

    default_test_dir = os.path.join(TOPDIR, PROJECT, 'test')

    def initialize_options(self):
        self.pytest_args = ''
        self.coverage = False
        self.match = None
        self.jobs = None
        self.report = None

    def finalize_options(self):
        self.test_args = [self.default_test_dir]
        self.coverage = bool(self.coverage)
        if self.match is not None:
            self.test_args.extend(['-k', self.match])

        if self.coverage:
            try:
                import pytest_cov
                self.test_args.extend(['--cov', PROJECT])
            except ImportError:
                sys.stderr.write('error: install pytest-cov for coverage support\n')
                sys.exit(1)

            if self.report is None:
                # disable coverage report output
                self.test_args.extend(['--cov-report='])
            else:
                self.test_args.extend(['--cov-report', self.report])

        if self.jobs is not None:
            try:
                import xdist
                self.test_args.extend(['-n', self.jobs])
            except ImportError:
                sys.stderr.write('error: install pytest-xdist for -j/--jobs support\n')
                sys.exit(1)

        # add custom pytest args
        self.test_args.extend(shlex.split(self.pytest_args))

    def run(self):
        try:
            import pytest
        except ImportError:
            sys.stderr.write('error: pytest is not installed\n')
            sys.exit(1)

        # build extensions and byte-compile python
        build_ext = self.reinitialize_command('build_ext')
        build_py = self.reinitialize_command('build_py')
        build_ext.ensure_finalized()
        build_py.ensure_finalized()
        self.run_command('build_ext')
        self.run_command('build_py')

        # Change the current working directory to the builddir during testing
        # so coverage paths are correct.
        builddir = os.path.abspath(build_py.build_lib)
        if self.coverage and os.path.exists(os.path.join(TOPDIR, '.coveragerc')):
            shutil.copyfile(os.path.join(TOPDIR, '.coveragerc'),
                            os.path.join(builddir, '.coveragerc'))
        ret = subprocess.call([sys.executable, '-m', 'pytest'] + self.test_args, cwd=builddir)
        sys.exit(ret)


def print_check(message, if_yes='found', if_no='not found'):
    """Decorator to print pre/post-check messages."""
    def sub_decorator(f):
        def sub_func(*args, **kwargs):
            sys.stderr.write('-- %s\n' % (message,))
            result = f(*args, **kwargs)
            sys.stderr.write(
                '-- %s -- %s\n' % (message, if_yes if result else if_no))
            return result
        sub_func.pkgdist_config_decorated = True
        return sub_func
    return sub_decorator


def cache_check(cache_key):
    """Method decorate to cache check result."""
    def sub_decorator(f):
        def sub_func(self, *args, **kwargs):
            if cache_key in self.cache:
                return self.cache[cache_key]
            result = f(self, *args, **kwargs)
            self.cache[cache_key] = result
            return result
        sub_func.pkgdist_config_decorated = True
        return sub_func
    return sub_decorator


def check_define(define_name):
    """Method decorator to store check result."""
    def sub_decorator(f):
        @cache_check(define_name)
        def sub_func(self, *args, **kwargs):
            result = f(self, *args, **kwargs)
            self.check_defines[define_name] = result
            return result
        sub_func.pkgdist_config_decorated = True
        return sub_func
    return sub_decorator


class config(dst_config.config):
    """Perform platform checks for extension build."""

    user_options = dst_config.config.user_options + [
        ("cache-path", "C", "path to read/write configuration cache"),
    ]

    def initialize_options(self):
        self.cache_path = None
        self.build_base = None
        dst_config.config.initialize_options(self)

    def finalize_options(self):
        if self.cache_path is None:
            self.set_undefined_options(
                'build',
                ('build_base', 'build_base'))
            self.cache_path = os.path.join(self.build_base, 'config.cache')
        dst_config.config.finalize_options(self)

    def _cache_env_key(self):
        return (self.cc, self.include_dirs, self.libraries, self.library_dirs)

    @cache_check('_sanity_check')
    @print_check('Performing basic C toolchain sanity check', 'works', 'broken')
    def _sanity_check(self):
        return self.try_link("int main(int argc, char *argv[]) { return 0; }")

    def run(self):
        from snakeoil.pickling import dump, load

        # try to load the cached results
        try:
            with open(self.cache_path, 'rb') as f:
                cache_db = load(f)
        except (OSError, IOError):
            cache_db = {}
        else:
            if self._cache_env_key() == cache_db.get('env_key'):
                sys.stderr.write('-- Using cache from %s\n' % self.cache_path)
            else:
                sys.stderr.write('-- Build environment changed, discarding cache\n')
                cache_db = {}

        self.cache = cache_db.get('cache', {})
        self.check_defines = {}

        if not self._sanity_check():
            sys.stderr.write('The C toolchain is unable to compile & link a simple C program!\n')
            sys.exit(1)

        # run all decorated methods
        for k in dir(self):
            if k.startswith('_'):
                continue
            if hasattr(getattr(self, k), 'pkgdist_config_decorated'):
                getattr(self, k)()

        # store results in Distribution instance
        self.distribution.check_defines = self.check_defines
        # store updated cache
        cache_db = {
            'cache': self.cache,
            'env_key': self._cache_env_key(),
        }
        self.mkpath(os.path.dirname(self.cache_path))
        with open(self.cache_path, 'wb') as f:
            dump(cache_db, f)

    # == methods for custom checks ==
    def check_struct_member(self, typename, member, headers=None, include_dirs=None, lang="c"):
        """Check whether typename (must be struct or union) has the named member."""
        return self.try_compile(
            'int main() { %s x; (void) x.%s; return 0; }'
            % (typename, member), headers, include_dirs, lang)


# yes these are in snakeoil.compatibility; we can't rely on that module however
# since snakeoil source is in 2k form, but this module is 2k/3k compatible.
# in other words, it could be invoked by py3k to translate snakeoil to py3k
is_py3k = sys.version_info >= (3, 0)
is_jython = 'java' in getattr(sys, 'getPlatform', lambda: '')().lower()
