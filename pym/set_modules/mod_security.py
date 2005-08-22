#!/usr/bin/python

import sets
import sys, os
sys.path.insert(0, "/usr/lib/gentoolkit/pym")
import glsa

class GLSAList(sets.BaseSet):
	def __init__(self, name, glsaconfig):
		self.__config = glsaconfig
		self._name = name
		self._capabilities = 0
		self._entries = []
	
	def _sync(self, mode):
		if mode != "r":
			return
		# build glsa lists
		completelist = glsa.get_glsa_list(self.__config["GLSA_DIR"], self.__config)

		if os.access(self.__config["CHECKFILE"], os.R_OK):
			checklist = [line.strip() for line in open(self.__config["CHECKFILE"], "r").readlines()]
		else:
			checklist = []
		glsalist = [e for e in completelist if e not in checklist]
		for g in glsalist:
			myglsa = glsa.Glsa(g, self.__config)
			for x in myglsa.getMergeList():
				if not "="+x in self._entries:
					self._entries.append("="+x)
