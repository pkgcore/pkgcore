#!/usr/bin/env python

import errno
import io
from itertools import chain
import operator
import os
import re
import subprocess
import sys

from distutils import log
from distutils.command.build import build
from distutils.errors import DistutilsExecError
from distutils.util import byte_compile
from setuptools import Command, setup, find_packages
from setuptools.command import install

import pkgdist

# These offsets control where we install the pkgcore config files and the EBD
# bits relative to the install-data path given to the install subcmd.
DATA_INSTALL_OFFSET = 'share/pkgcore'
CONFIG_INSTALL_OFFSET = os.path.join(DATA_INSTALL_OFFSET, 'config')
LIBDIR_INSTALL_OFFSET = 'lib/pkgcore'
EBD_INSTALL_OFFSET = os.path.join(LIBDIR_INSTALL_OFFSET, 'ebd')

# top level repo/tarball directory
TOPDIR = os.path.dirname(os.path.abspath(__file__))


class mysdist(pkgdist.sdist):

    """sdist command specifying the right files."""

    def make_release_tree(self, base_dir, files):
        """Create and populate the directory tree that is put in source tars.

        This copies or hardlinks "normal" source files that should go
        into the release and adds generated files that should not
        exist in a working tree.
        """
        import shutil

        # this is icky, but covers up cwd changing issues.
        cwd = os.getcwd()

        # generate bash function lists so they don't need to be created at
        # install time
        write_pkgcore_ebd_funclists('/', 'bash', os.path.join(cwd, 'bin'))
        shutil.copytree(os.path.join(cwd, 'bash', 'funcnames'),
                        os.path.join(base_dir, 'bash', 'funcnames'))

        pkgdist.sdist.make_release_tree(self, base_dir, files)


class pkgcore_build(build):

    user_options = build.user_options[:]
    user_options.append(('enable-man-pages', None, 'build man pages'))
    user_options.append(('enable-html-docs', None, 'build html docs'))

    boolean_options = build.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    sub_commands = build.sub_commands[:]
    sub_commands.append(('build_scripts', None))
    sub_commands.append(('build_docs', operator.attrgetter('enable_html_docs')))
    sub_commands.append(('build_man', operator.attrgetter('enable_man_pages')))

    def initialize_options(self):
        build.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        build.finalize_options(self)
        if self.enable_man_pages is None:
            path = os.path.dirname(os.path.abspath(__file__))
            self.enable_man_pages = not os.path.exists(os.path.join(path, 'man'))

        if self.enable_html_docs is None:
            self.enable_html_docs = False


def _get_files(path):
    for root, dirs, files in os.walk(path):
        for f in files:
            yield os.path.join(root, f)[len(path):].lstrip('/')


def _get_data_mapping(host_path, path, skip=None):
    skip = list(skip) if skip is not None else []
    for root, dirs, files in os.walk(path):
        yield (os.path.join(host_path, root.partition(path)[2].lstrip('/')),
               [os.path.join(root, x) for x in files
                if os.path.join(root, x) not in skip])


class pkgcore_install_docs(Command):

    """Install html documentation"""

    content_search_path = ('build/sphinx/html', 'html')
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
            self.prefix, 'share', 'doc', 'pkgcore-%s' % __version__, 'html')

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
        self.content = self._map_paths(_get_files(self.source_path))
        return self.content

    def run(self, firstrun=True):
        self.source_path = self.find_content()
        if self.source_path is None:
            if not firstrun:
                raise DistutilsExecError(
                    "no pregenerated sphinx content, and sphinx isn't available "
                    "to generate it; bailing")
            cwd = os.getcwd()
            if subprocess.call([sys.executable, 'setup.py', self.build_command], cwd=cwd):
                raise DistutilsExecError("%s failed" % self.build_command)
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


class pkgcore_install_man(pkgcore_install_docs):

    """Install man pages"""

    content_search_path = ('build/sphinx/man', 'man')
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

_base_install = getattr(pkgdist, 'install', install.install)


class pkgcore_install(_base_install):

    user_options = _base_install.user_options[:]
    user_options.append(('enable-man-pages', None, 'install man pages'))
    user_options.append(('enable-html-docs', None, 'install html docs'))

    boolean_options = _base_install.boolean_options[:]
    boolean_options.extend(['enable-man-pages', 'enable-html-docs'])

    def initialize_options(self):
        _base_install.initialize_options(self)
        self.enable_man_pages = False
        self.enable_html_docs = False

    def finalize_options(self):
        build_options = self.distribution.command_options.setdefault('build', {})
        build_options['enable_html_docs'] = ('command_line', self.enable_html_docs and 1 or 0)
        man_pages = self.enable_man_pages
        if man_pages and os.path.exists('man'):
            man_pages = False
        build_options['enable_man_pages'] = ('command_line', man_pages and 1 or 0)
        _base_install.finalize_options(self)

    sub_commands = _base_install.sub_commands[:]
    sub_commands.append(('install_man', operator.attrgetter('enable_man_pages')))
    sub_commands.append(('install_docs', operator.attrgetter('enable_html_docs')))

    def run(self):
        _base_install.run(self)
        target = self.install_data
        root = self.root or '/'
        if target.startswith(root):
            target = os.path.join('/', os.path.relpath(target, root))
        if not self.dry_run:
            # Install configuration data so pkgcore knows where to find it's content,
            # rather than assuming it is running from a tarball/git repo.
            write_pkgcore_lookup_configs(self.install_purelib, target)

            # Generate ebd function lists used for environment filtering if
            # they don't exist (release tarballs contain pre-generated files).
            if not os.path.exists(os.path.join(os.getcwd(), 'bash', 'funcnames')):
                write_pkgcore_ebd_funclists(
                    root, os.path.join(target, EBD_INSTALL_OFFSET), self.install_scripts)


def write_pkgcore_ebd_funclists(root, target, scripts_dir):
    ebd_dir = target
    if root != '/':
        ebd_dir = os.path.join(root, os.path.abspath(target).lstrip('/'))
    log.info("Writing ebd function lists to %s" % os.path.join(ebd_dir, 'funcnames'))
    try:
        os.makedirs(os.path.join(ebd_dir, 'funcnames'))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    # add scripts dir to PATH for filter-env usage in global scope
    env = {'PATH': os.pathsep.join([scripts_dir, os.environ.get('PATH', '')])}

    # generate global function list
    with open(os.devnull, 'w') as devnull:
        with open(os.path.join(ebd_dir, 'funcnames', 'global'), 'w') as f:
            if subprocess.call(
                    [os.path.join(os.getcwd(), 'bash', 'generate_global_func_list.bash')],
                    cwd=ebd_dir, env=env, stdout=f):
                raise DistutilsExecError("generating global function list failed")

    # generate EAPI specific function lists
    eapis = (x.split('.')[0] for x in os.listdir(os.path.join(ebd_dir, 'eapi'))
             if x.split('.')[0].isdigit())
    for eapi in sorted(eapis):
        with open(os.path.join(ebd_dir, 'funcnames', eapi), 'w') as f:
            if subprocess.call(
                    [os.path.join(os.getcwd(), 'bash', 'generate_eapi_func_list.bash'), eapi],
                    cwd=ebd_dir, env=env, stdout=f):
                raise DistutilsExecError(
                    "generating EAPI %s function list failed" % eapi)


def write_pkgcore_lookup_configs(python_base, install_prefix, injected_bin_path=()):
    path = os.path.join(python_base, "pkgcore", "_const.py")
    log.info("Writing lookup configuration to %s" % path)
    with open(path, "w") as f:
        os.chmod(path, 0o644)
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
    byte_compile([path], prefix=python_base)
    byte_compile([path], optimize=2, prefix=python_base)


class test(pkgdist.test):

    def run(self):
        # This is fairly hacky, but is done to ensure that the tests
        # are ran purely from what's in build, reflecting back to the source
        # only for misc bash scripts or config data.
        key = 'PKGCORE_OVERRIDE_DATA_PATH'
        original = os.environ.get(key)
        try:
            os.environ[key] = os.path.dirname(os.path.realpath(__file__))
            return pkgdist.test.run(self)
        finally:
            if original is not None:
                os.environ[key] = original
            else:
                os.environ.pop(key, None)


extensions = []
if not pkgdist.is_py3k:
    extensions.extend([
        pkgdist.OptionalExtension(
            'pkgcore.ebuild._atom', ['src/atom.c']),
        pkgdist.OptionalExtension(
            'pkgcore.ebuild._cpv', ['src/cpv.c']),
        pkgdist.OptionalExtension(
            'pkgcore.ebuild._depset', ['src/depset.c']),
        pkgdist.OptionalExtension(
            'pkgcore.ebuild._filter_env', [
                'src/filter_env.c', 'src/bmh_search.c']),
        pkgdist.OptionalExtension(
            'pkgcore.restrictions._restrictions', ['src/restrictions.c']),
        pkgdist.OptionalExtension(
            'pkgcore.ebuild._misc', ['src/misc.c']),
    ])

cmdclass = {
    'sdist': mysdist,
    'build': pkgcore_build,
    'build_py': pkgdist.build_py,
    'build_ext': pkgdist.build_ext,
    'build_man': pkgdist.build_man,
    'test': test,
    'install': pkgcore_install,
    'build_scripts': pkgdist.build_scripts,
    'install_man': pkgcore_install_man,
    'install_docs': pkgcore_install_docs,
}
command_options = {}

version = ''
with io.open('pkgcore/__init__.py', encoding='utf-8') as f:
    version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                        f.read(), re.MULTILINE).group(1)

if not version:
    raise RuntimeError('Cannot find version')


with io.open('README.rst', encoding='utf-8') as f:
    readme = f.read()

setup(
    name='pkgcore',
    version=version,
    description='package managing framework',
    long_description=readme,
    url='https://github.com/pkgcore/pkgcore',
    license='BSD/GPLv2',
    author='Brian Harring, Tim Harder',
    author_email='pkgcore-dev@googlegroups.com',
    packages=find_packages(),
    setup_requires=['snakeoil>=0.6.6'],
    install_requires=['snakeoil>=0.6.6'],
    scripts=os.listdir('bin'),
    data_files=list(chain(
        _get_data_mapping(CONFIG_INSTALL_OFFSET, 'config'),
        _get_data_mapping(EBD_INSTALL_OFFSET, 'bash'),
    )),
    ext_modules=extensions, cmdclass=cmdclass, command_options=command_options,
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)
