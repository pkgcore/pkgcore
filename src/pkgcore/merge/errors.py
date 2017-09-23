# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
exceptions thrown by the MergeEngine
"""

__all__ = ("ModificationError", "BlockModification",
    "TriggerUnknownCset",
)

class ModificationError(Exception):

    """Base Exception class for modification errors"""

    def __init__(self, trigger, msg):
        self.trigger = trigger
        self.msg = msg
        Exception.__init__(self, "%s: modification error: %s" %
            (self.trigger, self.msg))


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
        ModificationError.__init__(self, "%s: trigger %r unknown cset: %r" %
                                   (self.__class__, trigger, csets))
        self.trigger, self.csets = trigger, csets
