#!/usr/bin/python

import sets
import os.path

class SystemList(sets.BaseSet):
	def __init__(self, profilelist):
		self.__profiles = profilelist
		self._name = "system"
		self._capabilities = 0
		self._entries = []
		
	def _sync(self, mode):
		if mode != "r":
			return
		for p in self.__profiles:
			if os.path.exists(p+"/packages"):
				packages = open(p+"/packages", "r").read().split("\n")
			else:
				continue
			for pkg in [x[1:] for x in packages if len(x) > 1 and x[0] == "*"]:
				if not pkg in self._entries:
					self._entries.append(pkg)
			for pkg in [x[2:] for x in packages if len(x) > 2 and x[:2] == "-*"]:
				if pkg in self._entries:
					self._entries.remove(pkg)
