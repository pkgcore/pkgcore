# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
package class for buildable ebuilds
"""

from pkgcore.util.currying import post_curry
from pkgcore.util.demandload import demandload
demandload(globals(),
    "pkgcore.util.xml:etree "
    "pkgcore.ebuild:digest "
    "pkgcore.util:mappings ")


class MetadataXml(object):
    """
    metadata.xml parsed reseults
    
    attributes are set to -1 if unloaded, None if no entry, or the value
    if loaded
    
    """
    
    __slots__ = ("__weakref__", "_maintainers", "_herds", "_longdescription",
        "_source")
    
    
    def __init__(self, source):
        self._source = source

    def _generic_attr(self, attr):
        if self._source is not None:
            self._parse_xml()
        return getattr(self, attr)

    for attr in ("herds", "maintainers", "longdescription"):
        locals()[attr] = property(post_curry(_generic_attr, "_"+attr))
    del attr

    def _parse_xml(self):
        tree = etree.parse(self._source.get_fileobj())
        maintainers = []
        for x in tree.findall("maintainer"):
            name = email = None
            for e in x:
                if e.tag == "name":
                    name = e.text
                elif e.tag == "email":
                    email = e.text
            if name is not None:
                if email is not None:
                    maintainers.append("%s <%s>" % (name, email))
                else:
                    maintainers.append(name)
            elif email is not None:
                maintainers.append(email)

        self._maintainers = tuple(maintainers)
        self._herds = tuple(str(x.text)
            for x in tree.findall("herd"))

        # Could be unicode!
        longdesc = tree.findtext("longdescription")
        if longdesc:
            longdesc = ' '.join(longdesc.strip().split())
        self._longdescription = longdesc
        self._source = None


class Manifest(object):
    
    def __init__(self, source, enforce_gpg=False):
        self._source = (source, not enforce_gpg)

    def _pull_manifest(self):
        if self._source is None:
            return
        source, gpg = self._source
        data = digest.parse_manifest(source, ignore_gpg=gpg,
            kls_override=mappings.ImmutableDict)
        self._dist, self._aux, self._ebuild, self._misc = data[0]
        self._version = data[1]
        self._source = None
    
    @property
    def version(self):
        self._pull_manifest()
        return self._version
    
    @property
    def required_files(self):
        self._pull_manifest()
        return mappings.StackedDict(self._ebuild, self._misc)

    @property
    def aux_files(self):
        self._pull_manifest()
        return self._aux

    @property
    def distfiles(self):
        self._pull_manifest()
        if self.version != 2:
            raise TypeError("only manifest2 instances carry digest data")
        return self._dist


class SharedPkgData(object):

    __slots__ = ("__weakref__", "metadata_xml", "manifest")
    
    def __init__(self, metadata_xml, manifest):
        self.metadata_xml = metadata_xml
        self.manifest = manifest
