# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
chksum verification/generation subsystem
"""

from pkgcore.interfaces.data_source import base as base_data_source
from snakeoil.demandload import demandload
demandload(globals(), "os",
    "sys",
    "pkgcore.log:logger",
    "pkgcore.chksum.defaults:loop_over_file",
    "snakeoil.modules:load_module",
    "snakeoil.osutils:listdir_files",
)

chksum_types = {}
__inited__ = False

def get_handler(requested):

    """
    get a chksum handler

    @raise KeyError: if chksum type has no registered handler
    @return: chksum handler (callable)
    """

    if not __inited__:
        init()
    if requested not in chksum_types:
        raise KeyError("no handler for %s" % requested)
    return chksum_types[requested]


def get_handlers(requested=None):

    """
    get chksum handlers

    @param requested: None (all handlers), or a sequence of the specific
        handlers desired.
    @raise KeyError: if requested chksum type has no registered handler
    @return: dict of chksum_type:chksum handler
    """

    if requested is None:
        if not __inited__:
            init()
        return dict(chksum_types)
    d = {}
    for x in requested:
        d[x] = get_handler(x)
    return d


def init(additional_handlers=None):

    """
    init the chksum subsystem.

    Scan the dir, find what handlers are available, etc.

    @param additional_handlers: None, or pass in a dict of type:func
    """

    global __inited__

    if additional_handlers is not None and not isinstance(
        additional_handlers, dict):
        raise TypeError("additional handlers must be a dict!")

    chksum_types.clear()
    __inited__ = False
    loc = os.path.dirname(sys.modules[__name__].__file__)
    for f in listdir_files(loc):
        if not f.endswith(".py") or f.startswith("__init__."):
            continue
        try:
            i = f.find(".")
            if i != -1:
                f = f[:i]
            del i
            m = load_module(__name__+"."+f)
        except ImportError:
            continue
        try:
            types = getattr(m, "chksum_types")
        except AttributeError:
            # no go.
            continue
        try:
            chksum_types.update(types)

        except ValueError:
            logger.warn(
                "%s.%s invalid chksum_types, ValueError Exception" % (
                    __name__, f))
            continue

    if additional_handlers is not None:
        chksum_types.update(additional_handlers)

    __inited__ = True


def get_chksums(location, *chksums):
    """
    run multiple chksumers over a data_source/file path
    """
    handlers = get_handlers(chksums)
    # try to hand off to the per file handler, may be faster.
    if len(chksums) == 1:
        return [handlers[chksums[0]](location)]
    return loop_over_file(location, *[handlers[k].new() for k in chksums])
