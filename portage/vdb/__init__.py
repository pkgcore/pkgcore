# Copyright: 2005 Gentoo Foundation
# Author(s): Jeff Oliver (kaiserfro@yahoo.com)
# License: GPL2
# $Id: __init__.py 2126 2005-10-13 06:51:30Z ferringb $
from portage.repository import multiplex
from repository import tree as vdb_repository
from virtualrepository import tree as virtualrepository

def repository(*args, **kwargs):
	r = vdb_repository(*args, **kwargs)
	return multiplex.tree(r, virtualrepository(r))
