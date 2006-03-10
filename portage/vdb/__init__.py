# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2
# $Id: __init__.py 2285 2005-11-10 00:36:17Z ferringb $

from portage.repository import multiplex
from repository import tree as vdb_repository
from virtualrepository import tree as virtualrepository

def repository(*args, **kwargs):
	r = vdb_repository(*args, **kwargs)
	return multiplex.tree(r, virtualrepository(r))
