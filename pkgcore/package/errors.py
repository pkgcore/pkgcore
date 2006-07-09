# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


class InvalidCpv(ValueError):
	"""Raised if an invalid cpv was passed in.

	@ivar args: single-element tuple containing the invalid string.
	@type args: C{tuple}
	"""
