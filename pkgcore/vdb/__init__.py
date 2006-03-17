# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.repository import multiplex
from ondisk import tree as vdb_repository
from virtual import tree as virtualrepository

def repository(*args, **kwargs):
	r = vdb_repository(*args, **kwargs)
	return multiplex.tree(r, virtualrepository(r))
