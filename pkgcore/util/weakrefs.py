# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

# Unused import
# pylint: disable-msg=W0611

try:
    # No name in module
    # pylint: disable-msg=E0611
    from pkgcore.util._caching import WeakValCache
except ImportError:
    from weakref import WeakValueDictionary as WeakValCache
