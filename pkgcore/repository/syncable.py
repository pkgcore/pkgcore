# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base

__all__ = ("tree_mixin",)

class tree_mixin(object):

    def __init__(self, sync=None):
        self._syncer = sync
