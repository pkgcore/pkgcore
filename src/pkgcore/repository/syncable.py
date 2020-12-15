__all__ = ("tree",)

from ..operations.repo import sync_operations


class tree:

    operations_kls = sync_operations

    def __init__(self, sync=None):
        object.__setattr__(self, '_syncer', sync)

    @property
    def operations(self):
        return self.get_operations()

    def get_operations(self, observer=None):
        return self.operations_kls(self)

    def _pre_sync(self):
        """Run any required pre-sync repo operations."""

    def _post_sync(self):
        """Run any required post-sync repo operations."""
