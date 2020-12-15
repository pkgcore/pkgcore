"""
Internal constants.
"""

import os
import sys

from snakeoil import mappings

from . import __title__

osp = os.path
_reporoot = osp.realpath(__file__).rsplit(os.path.sep, 3)[0]
_module = sys.modules[__name__]

try:
    # This is a file written during pkgcore installation;
    # if it exists, we defer to it.  If it doesn't, then we're
    # running from a git checkout or a tarball.
    from . import _const as _defaults
except ImportError:
    _defaults = object()


def _GET_CONST(attr, default_value, allow_environment_override=False):
    consts = mappings.ProxiedAttrs(_module)
    is_tuple = not isinstance(default_value, str)
    if is_tuple:
        default_value = tuple(x % consts for x in default_value)
    else:
        default_value %= consts

    result = getattr(_defaults, attr, default_value)
    if allow_environment_override:
        result = os.environ.get(f'PKGCORE_OVERRIDE_{attr}', result)
    if is_tuple:
        result = tuple(result)
    return result


# determine XDG compatible paths
for xdg_var, var_name, fallback_dir in (
        ('XDG_CONFIG_HOME', 'USER_CONFIG_PATH', '~/.config'),
        ('XDG_CACHE_HOME', 'USER_CACHE_PATH', '~/.cache'),
        ('XDG_DATA_HOME', 'USER_DATA_PATH', '~/.local/share')):
    setattr(_module, var_name,
            os.environ.get(xdg_var, osp.join(osp.expanduser(fallback_dir), __title__)))

USER_CONF_FILE = osp.join(getattr(_module, 'USER_CONFIG_PATH'), 'pkgcore.conf')
SYSTEM_CONF_FILE = '/etc/pkgcore/pkgcore.conf'
SYSTEM_CACHE_PATH = '/var/cache/pkgcore'

REPO_PATH = _GET_CONST('REPO_PATH', _reporoot, allow_environment_override=True)
DATA_PATH = _GET_CONST('DATA_PATH', '%(REPO_PATH)s/data')
LIBDIR_PATH = _GET_CONST('LIBDIR_PATH', '%(REPO_PATH)s')
CONFIG_PATH = _GET_CONST('CONFIG_PATH', '%(REPO_PATH)s/data/config')
PATH_FORCED_PREPEND = _GET_CONST('INJECTED_BIN_PATH', ('%(REPO_PATH)s/bin',))
CP_BINARY = _GET_CONST('CP_BINARY', '/bin/cp')
