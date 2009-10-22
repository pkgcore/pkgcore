# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from pkgcore.sync import base

class tree_mixin(object):

    def __init__(self, sync=None):
        self._syncer = sync

    def sync(self, status_obj=None, force=False):
        # often enough, the syncer is a lazy_ref
        syncer = self._syncer
        if not isinstance(syncer, base.syncer):
            syncer = syncer.instantiate()
        return syncer.sync(force=force)

    @property
    def syncable(self):
        return self.operations.supports("sync")
        return self._syncer is not None
