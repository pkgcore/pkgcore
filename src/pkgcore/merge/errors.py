"""
exceptions thrown by the MergeEngine
"""

__all__ = ("ModificationError", "BlockModification", "TriggerUnknownCset")


from ..exceptions import PkgcoreException


class ModificationError(PkgcoreException):
    """Base Exception class for modification errors"""

    def __init__(self, trigger, msg):
        self.trigger = trigger
        self.msg = msg
        super().__init__(f"{self.trigger}: modification error: {self.msg}")


class BlockModification(ModificationError):
    """Merging cannot proceed"""

    def __str__(self):
        return "Modification was blocked by %s: %s" % (
            self.trigger.__class__.__name__, self.msg)

class TriggerUnknownCset(ModificationError):
    """Trigger's required content set isn't known"""

    def __init__(self, trigger, csets):
        if not isinstance(csets, (tuple, list)):
            csets = (csets,)
        super().__init__(
            f"{self.__class__}: trigger {trigger!r} unknown cset: {csets!r}")
        self.trigger, self.csets = trigger, csets
