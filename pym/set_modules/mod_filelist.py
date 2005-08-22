#!/usr/bin/python

import sets

class FileList(sets.BaseSet):
	def __init__(self, name, path):
		self.__path = path
		self._name = name
		self._capabilities = sets.BaseSet.TARGET_UPDATABLE
		self._entries = []
	
	def _sync(self, mode):
		# mode == "r": update internal entry list from file
		# mode == "w": write internal entry list to file
		# mode == "rw": write internal entry list to file and reread it
		if mode not in ["r", "w", "rw"]:
			return
		myfile = open(self.__path, mode)
		if mode in ["w", "rw"]:
			myfile.writelines([x+'\n' for x in self.__entries])
		if mode == "rw":
			# reopening the file to make sure we're in a consistent state
			myfile.close()
			myfile = open(self.__path, mode)
		if mode in ["r", "rw"]:
			self._entries = [x[:-1] for x in myfile.readlines()]
		myfile.close()
