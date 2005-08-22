#!/usr/bin/python

class BaseSet:

	TARGET_UPDATABLE = 1

	def __init__(self, name):
		pass

	def _sync(self, mode):
		# mode == "r": read entry list
		# mode == "w": write entry list
		# mode == "rw": write and reread entry list
		pass

	def addEntry(self, newentry):
		if not self.isCapable(self.TARGET_UPDATABLE):
			return
		self._sync(mode="r")
		if not newentry in self._entries:
			self._entries.add(newentry)
		self._sync(mode="rw")
	
	def removeEntry(self, entry):
		if not self.isCapable(self.TARGET_UPDATABLE):
			return
		self._sync(mode="r")
		if entry in self._entries:
			self._entries.remove(entry)
		self._sync(mode="rw")
	
	def getList(self):
		self._sync(mode="r")
		return self._entries
		
	def isCapable(self, capability):
		return (self.__capabilities & capability)
