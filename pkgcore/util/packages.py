# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

def get_raw_pkg(pkg):
	p = pkg
	while hasattr(p, "_raw_pkg"):
		p = p._raw_pkg
	return p
