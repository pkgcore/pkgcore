# Copyright: 2006-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
package class for buildable ebuilds
"""

from snakeoil.currying import post_curry
from snakeoil.compatibility import any
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin, listdir_files
from snakeoil.caching import WeakInstMeta
from itertools import chain
demandload(globals(),
    'snakeoil.xml:etree',
    'pkgcore.ebuild:digest',
    'pkgcore.log:logger',
    'snakeoil:mappings',
    'snakeoil:fileutils',
    'errno',
)


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

class Licenses(object):

    __metaclass__ = WeakInstMeta
    __inst_caching__ = True

    __slots__ = ('_base', '_licenses', '_groups')

    licenses_dir = 'licenses'
    license_group_location = 'profiles/license_groups'

    def __init__(self, repo_base):
        object.__setattr__(self, '_base', repo_base)
        object.__setattr__(self, '_licenses', None)
        object.__setattr__(self, '_groups', None)

    @property
    def licenses(self):
        if self._licenses is None:
            object.__setattr__(self, '_licenses', self._load_licenses())
        return self._licenses

    def _load_licenses(self):
        try:
            content = listdir_files(pjoin(self._base,
                self.licenses_dir))
        except (OSError, IOError):
            content = ()
        return frozenset(content)

    @property
    def groups(self):
        if self._groups is None:
            object.__setattr__(self, '_groups', self._load_groups())
        return self._groups

    def _load_groups(self):
        try:
            fp = pjoin(self._base, self.license_group_location)
            d = fileutils.read_dict(fp, splitter=' ')
        except (IOError, OSError):
            return mappings.ImmutableDict()
        except fileutils.ParseError, pe:
            logger.error("failed parsing license_groups: %s", pe)
            return mappings.ImmutableDict()
        self._expand_groups(d)
        return mappings.ImmutableDict((k, tuple(v))
            for (k,v) in d.iteritems())

    def _expand_groups(self, groups):
        keep_going = True
        for k,v in groups.iteritems():
            groups[k] = v.split()
        while keep_going:
            keep_going = False
            for k, v in groups.iteritems():
                if not any(x[0] == '@' for x in v):
                    continue
                keep_going = True
                l = []
                for v2 in v:
                    if v2[0] == '@':
                        v2 = v2[1:]
                        if not v2 or v2 not in groups:
                            logger.error("invalid license group reference: %r in %s",
                                v2, self)
                            continue
                        elif v2 == k:
                            logger.error("cyclic license group references for %r in %s",
                                v2, self)
                            continue
                        l.extend(groups[v2])
                    else:
                        l.append(v2)
                groups[k] = l

    def refresh(self):
        self._licenses = None
        self._groups = None

    def __getitem__(self, license):
        if not license in self:
            raise KeyError(license)
        try:
            return open(pjoin(self._base, self.licenses_dir, license)).read()
        except (OSError, IOError):
            raise KeyError(license)

    def __iter__(self):
        return iter(self.licenses)

    def __contains__(self, license):
        return license in self.licenses


class OverlayedLicenses(Licenses):

    __inst_caching__ = True
    __slots__ = ('_license_instances', '_license_sources')

    def __init__(self, *license_sources):
        object.__setattr__(self, '_license_sources', license_sources)
        object.__setattr__(self, '_licenses', None)
        object.__setattr__(self, '_groups', None)
        self._load_license_instances()

    def _load_groups(self):
        d = {}
        for li in self._license_instances:
            for k,v in li.groups.iteritems():
                if k in d:
                    d[k] += v
                else:
                    d[k] = v
        return d

    def _load_licenses(self):
        return frozenset(chain(*map(iter, self._license_instances)))

    def __getitem__(self, license):
        for li in self._license_instances:
            try:
                return li[license]
            except KeyError:
                pass
        raise KeyError(license)

    def refresh(self):
        for li in self._license_instances:
            li.refresh()
        self._load_license_instances()
        Licenses.refresh(self)

    def _load_license_instances(self):
        l = []
        for x in self._license_sources:
            if isinstance(x, Licenses):
                l.append(x)
            elif hasattr(x, 'licenses'):
                l.append(x.licenses)
        object.__setattr__(self, '_license_instances',
            tuple(l))
