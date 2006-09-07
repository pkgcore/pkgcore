#!/usr/bin/env python

import glob
import os, errno

from distutils import core, ccompiler, log
from distutils.command import build, sdist, install, build_py
from stat import ST_MODE

class mysdist(sdist.sdist):
	default_format = dict(sdist.sdist.default_format)
	default_format["posix"] = "bztar"

	def get_file_list(self):
		for key, globs in self.distribution.package_data.iteritems():
			for pattern in globs:
				self.filelist.extend(glob.glob(os.path.join(key, pattern)))
		self.filelist.append("ChangeLog")
		self.filelist.append("AUTHORS")
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
		objects = compiler.compile(list(
				os.path.join('src', 'filter-env', name)
				for name in ('main.c', 'bmh_search.c')), debug=self.debug)
		compiler.link(compiler.EXECUTABLE, objects, os.path.join(
				'pkgcore', 'bin', 'ebuild-env', 'filter-env'))


build.build.sub_commands.append(('build_filter_env', None))

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

	def set_chmod(self, fp):
		if self.dry_run:
			log.info("changing mode of %s", file)
		else:
			mode = ((os.stat(fp)[ST_MODE]) | 0555) & 07777
			log.info("changing mode of %s to %o", fp, mode)
			os.chmod(fp, mode)


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


core.setup(
	name='pkgcore',
	version='0',
	description='package managing framework',
	url='http://gentooexperimental.org/~ferringb/bzr/pkgcore/',
	packages=packages,
	package_data={
		'pkgcore': [
			'data/*',
			'bin/ebuild-env/*',
			'bin/ebuild-helpers/*',
			],
		'src': [
			'filter-env/*.c',
			'filter-env/*.h',
			'bsd-flags/*',
			'tbz2tool.c'
			],
		},
	# booo, no glob support in distutils for this one
	scripts=(
		glob.glob('pkgcore/bin/utilities/*.py') + 
		['pkgcore/bin/utilities/pquery',
		'pkgcore/bin/utilities/pquery2']),
	ext_modules=[
		core.Extension('pkgcore.util._caching', ['pkgcore/util/_caching.c']),
		core.Extension('pkgcore.util._lists', ['pkgcore/util/_lists.c']),
		core.Extension('pkgcore.ebuild._cpv', ['pkgcore/ebuild/_cpv.c']),
		core.Extension('pkgcore.util.osutils._readdir',
					   ['pkgcore/util/osutils/_readdir.c']),
		],
	cmdclass={'build_filter_env': build_filter_env, "sdist":mysdist, "build_py": hacked_build_py},
	)
