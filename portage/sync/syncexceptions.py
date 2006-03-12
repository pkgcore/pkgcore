# syncexceptions.py: base sync exception class. not used currently (should be though)
# Copyright 2004 Brian Harring <ferringb@gmail.com>
# Distributed under the terms of the GNU General Public License v2

class SyncException(Exception):
	"""base sync exception"""
	def __init__(self,value):
		self.value=value
	def __str__(self):
		return value
