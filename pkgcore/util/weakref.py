# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

try:
	from pkgcore.util._caching import WeakValCache
except ImportError:
	from weakref import WeakValueDictionary as WeakValCache
