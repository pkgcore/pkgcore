# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

# yuck. :)

class SystemSet(frozenset):
	def __new__(self, profile):
		return frozenset.__new__(self, profile.sys)
