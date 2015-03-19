# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
Internal constants.
"""

import os
osp = os.path
import sys
from snakeoil import mappings, compatibility
try:
    # This is a file written during pkgcore installation;
    # if it exists, we defer to it.  If it doesn't, then we're
    # running from a git checkout or a tarball.
    from pkgcore import _const as _defaults
except ImportError:
    _defaults = object()

# the pkgcore package directory
PKGCORE_BASE_PATH  = osp.dirname(osp.abspath(__file__))
SYSTEM_CONF_FILE   = '/etc/pkgcore.conf'
USER_CONF_FILE     = osp.expanduser('~/.pkgcore.conf')

SANDBOX_BINARY     = "/usr/bin/sandbox"

# should lift these from configuration, or PATH inspection.
BASH_BINARY        = "/bin/bash"
COPY_BINARY        = "/bin/cp"
PRELINK_BINARY     = "/usr/sbin/prelink"

HOST_NONROOT_PATHS = ("/usr/local/bin", "/usr/bin", "/bin")
HOST_ROOT_PATHS    = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin",
                      "/usr/bin", "/sbin", "/bin")

# no longer used.
LIBFAKEROOT_PATH   = "/usr/lib/libfakeroot.so"
FAKED_PATH         = "/usr/bin/faked"

VERSION            = '0.9'

def _GET_CONST(attr, default_value, allow_environment_override=False):
    consts = mappings.ProxiedAttrs(sys.modules[__name__])
    if compatibility.is_py3k:
        is_tuple = not isinstance(default_value, str)
    else:
        is_tuple = not isinstance(default_value, basestring)
    if is_tuple:
        default_value = tuple(x % consts for x in default_value)
    else:
        default_value %= consts

    result = getattr(_defaults, attr, default_value)
    if allow_environment_override:
        result = os.environ.get("PKGCORE_OVERRIDE_%s" % attr, result)
    if is_tuple:
        result = tuple(result)
    return result

DATA_PATH           = _GET_CONST('DATA_PATH',
                                osp.dirname(osp.dirname(osp.realpath(__file__))),
                                allow_environment_override=True)
PATH_FORCED_PREPEND = _GET_CONST('PATH_FORCED_PREPENDS', ('%(DATA_PATH)s/bin',))
