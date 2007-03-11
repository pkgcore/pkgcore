# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
indirection to load ElementTree
"""
# essentially... prefer cElementTree, then 2.5 bundled, then
# elementtree, then 2.5 bundled, then our own bundled

# "No name etree in module xml", "Reimport cElementTree"
# pylint: disable-msg=E0611,W0404

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

def escape(string):
    """
    simple escaping of &, <, and >
    """
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">",
                                                                     "&gt;")
