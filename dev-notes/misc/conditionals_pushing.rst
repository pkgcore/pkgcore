======================
 Conditionals pushing
======================

Need to classify restrictions as existance tests, either true/false::

	if conditional
		if negate:
			request_disable
		else
			request_enable

How does negation fit into this long view? Specifically, rolling
changes back? All potential conditionals of a package/format are
treated as lists; no straight booleans, beyond inserting a doffed
element and falling back to len test (may be changed, although any
format requiring a true boolean conditional need implement some
trickery).
