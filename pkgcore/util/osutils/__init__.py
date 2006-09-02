"""
os specific utilities, FS access mainly

not heavily used right now, but will shift functions over to it as time goes by
"""

try:
	from pkgcore.util.osutils import _readdir as module
except ImportError:
	from pkgcore.util.osutils import native_readdir as module

listdir = module.listdir
listdir_dirs = module.listdir_dirs
listdir_files = module.listdir_files

del module
