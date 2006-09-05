# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
exceptions thrown by the MergeEngine
"""

class ModificationError(Exception):

    """Base Exception class for modification errors/warnings"""

    def __init__(self, msg):
        Exception.__init__(self, "%s: %s" % (self.__class__, msg))
        self.msg = msg


class BlockModification(ModificationError):
    """Merging cannot proceed"""

class TriggerUnknownCset(ModificationError):
    """Trigger's required content set isn't known"""

    def __init__(self, trigger, csets):
        if not isinstance(csets, (tuple, list)):
            csets = (csets,)
        ModificationError.__init__(self, "%s: trigger %r unknown cset: %r" %
                                   (self.__class__, trigger, csets))
        self.trigger, self.csets = trigger, csets


class NonFatalModification(Exception):
    pass

class TriggerWarning(NonFatalModification):
    pass

