# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
exceptions thrown by the MergeEngine
"""

class ModificationError(Exception):

	"""Base Exception class for modification errors/warnings"""

	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		return "%s: %s" % (self.__class__, self.msg)


class BlockModification(ModificationError):
	"""Merging cannot proceed"""

class TriggerUnknownCset(ModificationError):
	"""Trigger's required content set isn't known"""

	def __init__(self, trigger, csets):
		if not isinstance(csets, (tuple, list)):
			csets = (csets,)
		self.trigger, self.csets = trigger, csets

	def __str__(self):
		return "%s: trigger %r unknown cset: %r" % (
			self.__class__, self.trigger, self.csets)


class NonFatalModification(Exception):
	pass

class TriggerWarning(NonFatalModification):
	pass

