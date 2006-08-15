"""
os specific utilities, FS access mainly

not heavily used right now, but will shift functions over to it as time goes by
"""

cpy_listdir = cpy_listdir_files = cpy_listdir_dirs = native_listdir = native_listdir_dirs = native_listdir_files = None

try:
	from _readdir import cpy_listdir, cpy_listdir_files, cpy_listdir_dirs
	listdir = cpy_listdir
	listdir_dirs = cpy_listdir_dirs
	listdir_files = cpy_listdir_files

except ImportError:
	from native_readdir import native_listdir, native_listdir_dirs, native_listdir_files
	listdir = native_listdir
	listdir_dirs = native_listdir_dirs
	listdir_files = native_listdir_files
