# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

# essentially... prefer cElementTree, then 2.5 bundled, then elementtree, then 2.5 bundled,
# then our own bundled

gotit = True
try:
	import cElementTree as etree
except ImportError:
	gotit = False
if not gotit:
	try:
		from xml.etree import cElementTree as etree
		gotit = True
	except ImportError:
		pass
if not gotit:
	try:
		from elementtree import ElementTree as etree
		gotit = True
	except ImportError:
		pass
if not gotit:
	try:
		from xml.etree import ElementTree as etree
		gotit = True
	except ImportError:
		pass

if not gotit:
	from pkgcore.util.xml.bundled_elementtree import ElementTree as etree
del gotit
