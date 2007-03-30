# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
package class for buildable ebuilds
"""

from snakeoil.currying import post_curry
from snakeoil.demandload import demandload
demandload(globals(),
    "snakeoil.xml:etree "
    "pkgcore.ebuild:digest "
    "snakeoil:mappings "
    "errno ")


class Maintainer(object):

    """Data on a single maintainer.

    At least one of email and name is not C{None}.

    @type email: C{unicode} object or C{None}
    @ivar email: email address.
    @type name: C{unicode} object or C{None}
    @ivar name: full name
    @type description: C{unicode} object or C{None}
    @ivar description: description of maintainership.
    """

    __slots__ = ('email', 'description', 'name')

    def __init__(self, email=None, name=None, description=None):
        if email is None and name is None:
            raise ValueError('need at least one of name and email')
        self.email = email
        self.name = name
        self.description = description

    def __str__(self):
        if self.name is not None:
            if self.email is not None:
                res = '%s <%s>' % (self.name, self.email)
            else:
                res = self.name
        else:
            res = self.email
        if self.description is not None:
            return '%s (%s)' % (res, self.description)
        return res


class MetadataXml(object):
    """metadata.xml parsed results

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

    def _parse_xml(self, source=None):
        if source is None:
            source = self._source.get_fileobj()
        tree = etree.parse(source)
        maintainers = []
        for x in tree.findall("maintainer"):
            name = email = description = None
            for e in x:
                if e.tag == "name":
                    name = e.text
                elif e.tag == "email":
                    email = e.text
                elif e.tag == 'description':
                    description = e.text
            maintainers.append(Maintainer(
                    name=name, email=email, description=description))

        self._maintainers = tuple(maintainers)
        self._herds = tuple(x.text for x in tree.findall("herd"))

        # Could be unicode!
        longdesc = tree.findtext("longdescription")
        if longdesc:
            longdesc = ' '.join(longdesc.strip().split())
        self._longdescription = longdesc
        self._source = None


class LocalMetadataXml(MetadataXml):

    __slots__ = ()

    def _parse_xml(self):
        try:
            MetadataXml._parse_xml(self, open(self._source, "rb", 32768))
        except IOError, oe:
            if oe.errno != errno.ENOENT:
                raise
            self._maintainers = ()
            self._herds = ()
            self._longdescription = None
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
