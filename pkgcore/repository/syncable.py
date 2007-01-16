# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.sync import base

class tree_mixin(object):

    def __init__(self, sync=None):
        self._sync = sync

    def sync(self, status_obj=None, force=False):
        # often enough, the syncer is a lazy_ref
        syncer = self._sync
        if not isinstance(syncer, base.syncer):
            syncer = syncer.instantiate()
        return syncer.sync(force=force)

    @property
    def syncable(self):
        return self._sync is not None
