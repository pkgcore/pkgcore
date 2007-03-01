# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""pkgcore plugins package."""

import sys
import os.path


# XXX Having this function here is a bit of a wart: it is used by
# other plugin packages (like the pkgcore-check one), but we cannot
# put it in pkgcore.plugin because that imports this package (circular
# import).

def extend_path(path, name):
    """Simpler version of the stdlib's L{pkgutil.extend_path}.

    It does not support ".pkg" files, and it does not require an
    __init__.py (this is important: we want only one thing (pkgcore
    itself) to install the __init__.py to avoid name clashes).

    It also modifies the "path" list in place (and returns C{None})
    instead of copying it and returning the modified copy.
    """
    if not isinstance(path, list):
        # This could happen e.g. when this is called from inside a
        # frozen package.  Return the path unchanged in that case.
        return
    # Reconstitute as relative path.
    pname = os.path.join(*name.split('.'))

    for entry in sys.path:
        if not isinstance(entry, basestring) or not os.path.isdir(entry):
            continue
        subdir = os.path.join(entry, pname)
        # XXX This may still add duplicate entries to path on
        # case-insensitive filesystems
        if subdir not in path:
            path.append(subdir)

extend_path(__path__, __name__)
