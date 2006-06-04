#!/usr/bin/env python

import glob
import os.path

from distutils import core, ccompiler
from distutils.command import build


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
        objects = compiler.compile(list(
                os.path.join('src', 'filter-env', name)
                for name in ('main.c', 'bmh_search.c')), debug=self.debug)
        compiler.link(compiler.EXECUTABLE, objects, os.path.join(
                'pkgcore', 'bin', 'ebuild-env', 'filter-env'))


build.build.sub_commands.append(('build_filter_env', None))


packages = []

for root, dirs, files in os.walk('pkgcore'):
    if '__init__.py' in files:
        package = root.replace(os.path.sep, '.')
        print 'adding package %r' % (package,)
        packages.append(package)



core.setup(
    name='pkgcore',
    version='dev',
    description='package managing framework',
    packages=packages,
    package_data={
        'pkgcore': [
            'data/*',
            'bin/ebuild-env/*',
            'bin/ebuild-helpers/*',
            ]},
    # booo, no glob support in distutils for this one
    scripts=(
        glob.glob('pkgcore/bin/utilities/*.py') + 
        ('pkgcore/bin/utilities/pquery')),
    cmdclass={'build_filter_env': build_filter_env},
    )
