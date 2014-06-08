# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
package class for buildable ebuilds
"""

__all__ = ("Maintainer", "MetadataXml", "LocalMetadataXml",
    "SharedPkgData", "Licenses", "OverlayedLicenses")

from snakeoil.caching import WeakInstMeta
from snakeoil import compatibility
from snakeoil.currying import post_curry
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin, listdir_files, listdir
from snakeoil.sequences import namedtuple
from snakeoil import mappings
from snakeoil import klass
from itertools import chain
from pkgcore.config import ConfigHint
from pkgcore.repository import syncable
demandload(globals(),
    'errno',
    'snakeoil.xml:etree',
    'snakeoil.bash:BashParseError,iter_read_bash,read_dict',
    'snakeoil.fileutils:readfile,readlines_ascii',
    'snakeoil.lists:iter_stable_unique',
    'pkgcore.log:logger',
    'pkgcore.ebuild:atom,profiles',
    "pkgcore.restrictions:packages",
)


class Maintainer(object):

    """Data on a single maintainer.

    At least one of email and name is not C{None}.

    :type email: C{unicode} object or C{None}
    :ivar email: email address.
    :type name: C{unicode} object or C{None}
    :ivar name: full name
    :type description: C{unicode} object or C{None}
    :ivar description: description of maintainership.
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
            source = self._source.bytes_fileobj()
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
            longdesc = ' '.join(longdesc.split())
        self._longdescription = longdesc
        self._source = None


class LocalMetadataXml(MetadataXml):

    __slots__ = ()

    def _parse_xml(self):
        try:
            MetadataXml._parse_xml(self, open(self._source, "rb", 32768))
        except EnvironmentError as oe:
            if oe.errno != errno.ENOENT:
                raise
            self._maintainers = ()
            self._herds = ()
            self._longdescription = None
            self._source = None


class SharedPkgData(object):

    __slots__ = ("__weakref__", "metadata_xml", "manifest")

    def __init__(self, metadata_xml, manifest):
        self.metadata_xml = metadata_xml
        self.manifest = manifest


class Licenses(object):

    __metaclass__ = WeakInstMeta
    __inst_caching__ = True

    __slots__ = ('_base', '_licenses', '_groups', 'license_groups_path', 'licenses_dir')

    def __init__(self, repo_base, profile_base='profiles', licenses_dir='licenses', license_groups='profiles/license_groups'):
        object.__setattr__(self, '_base', repo_base)
        object.__setattr__(self, 'license_groups_path', pjoin(repo_base, license_groups))
        object.__setattr__(self, 'licenses_dir', pjoin(repo_base, licenses_dir))

    @klass.jit_attr_none
    def licenses(self):
        try:
            content = listdir_files(self.licenses_dir)
        except EnvironmentError:
            content = ()
        return frozenset(content)

    @klass.jit_attr_none
    def groups(self):
        try:
            d = read_dict(self.license_groups_path, splitter=' ')
        except EnvironmentError:
            return mappings.ImmutableDict()
        except BashParseError as pe:
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
            return open(pjoin(self.licenses_dir, license)).read()
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                raise KeyError(license)
            raise

    def __iter__(self):
        return iter(self.licenses)

    def __contains__(self, license):
        return license in self.licenses


class OverlayedLicenses(Licenses):

    __inst_caching__ = True
    __slots__ = ('_license_instances', '_license_sources')

    def __init__(self, *license_sources):
        object.__setattr__(self, '_license_sources', license_sources)
        self._load_license_instances()

    @klass.jit_attr_none
    def groups(self):
        d = {}
        for li in self._license_instances:
            for k,v in li.groups.iteritems():
                if k in d:
                    d[k] += v
                else:
                    d[k] = v
        return d

    @klass.jit_attr_none
    def licenses(self):
        return frozenset(chain(*map(iter, self._license_instances)))

    def __getitem__(self, license):
        for li in self._license_instances:
            try:
                return li[license]
            except KeyError:
                pass
        raise KeyError(license)

    def refresh(self):
        self._load_license_instances()
        for li in self._license_instances:
            li.refresh()
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


class _immutable_attr_dict(mappings.ImmutableDict):

    __slots__ = ()

    mappings.inject_getitem_as_getattr(locals())


_KnownProfile = namedtuple("_KnownProfile", ['profile', 'status'])


class BundledProfiles(object):

    klass.inject_immutable_instance(locals())

    def __init__(self, profile_base, format='pms'):
        object.__setattr__(self, 'profile_base', profile_base)
        object.__setattr__(self, 'format', format)

    @klass.jit_attr
    def arch_profiles(self):
        d = mappings.defaultdict(list)
        fp = pjoin(self.profile_base, 'profiles.desc')
        try:
            for line in iter_read_bash(fp):
                l = line.split()
                try:
                    key, profile, status = l
                except ValueError:
                    logger.error(
                        "%s: line doesn't follow 'key profile status' form: %s",
                         fp, line)
                    continue
                # Normalize the profile name on the offchance someone slipped an extra /
                # into it.
                d[key].append(_KnownProfile(
                    '/'.join(filter(None, profile.split('/'))), status))
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
            logger.debug("No profile descriptions found at %r", fp)
        return mappings.ImmutableDict(
            (k, tuple(sorted(v))) for k, v in d.iteritems())

    def create_profile(self, node):
        return profiles.OnDiskProfile(self.profile_base, node)


class RepoConfig(syncable.tree):

    layout_offset = "metadata/layout.conf"

    default_hashes = ('size', 'sha256', 'sha512', 'whirlpool')

    klass.inject_immutable_instance(locals())

    __metaclass__ = WeakInstMeta
    __inst_caching__ = True

    pkgcore_config_type = ConfigHint(typename='raw_repo',
        types={'syncer':'lazy_ref:syncer'})

    def __init__(self, location, syncer=None, profiles_base='profiles'):
        object.__setattr__(self, 'location', location)
        object.__setattr__(self, 'profiles_base', pjoin(self.location, profiles_base))
        syncable.tree.__init__(self, syncer)
        self.parse_config()

    def load_config(self):
        path = pjoin(self.location, self.layout_offset)
        return read_dict(iter_read_bash(readlines_ascii(path, True, True)),
            source_isiter=True, strip=True, filename=path)

    def parse_config(self):
        data = self.load_config()

        sf = object.__setattr__

        hashes = data.get('manifest-hashes', '').lower().split()
        if hashes:
            hashes = ['size'] + hashes
            hashes = tuple(iter_stable_unique(hashes))
        else:
            hashes = self.default_hashes

        manifest_policy = data.get('use-manifests', 'strict').lower()
        d = {
            'disabled':(manifest_policy == 'false'),
            'strict':(manifest_policy == 'strict'),
            'thin':(data.get('thin-manifests', '').lower() == 'true'),
            'signed':(data.get('sign-manifests', 'true').lower() == 'true'),
            'hashes':hashes,
        }

        sf(self, 'manifests', _immutable_attr_dict(d))
        masters = data.get('masters')
        if masters is None:
            if self.repo_id != 'gentoo' and not self.is_empty:
                logger.warning("repository at %r, named %r, doesn't specify masters in metadata/layout.conf. "
                    "Defaulting to whatever repository is defined as 'default' (gentoo usually). "
                    "Please explicitly set the masters, or set masters = '' if the repository "
                    "is standalone.", self.location, self.repo_id)
        else:
            masters = tuple(iter_stable_unique(masters.split()))
        sf(self, 'masters', masters)
        sf(self, 'aliases', tuple(iter_stable_unique(data.get('aliases', '').split())))
        sf(self, 'eapis_deprecated', tuple(iter_stable_unique(data.get('eapis-deprecated', '').split())))

        v = set(data.get('cache-formats', 'pms').lower().split())
        if not v.intersection(['pms', 'md5-dict']):
            v = 'pms'
        sf(self, 'cache_format', list(v)[0])

        v = set(data.get('profile-formats', 'pms').lower().split())
        if not v:
            # dumb ass overlay devs, treat it as missing.
            v = set(['pms'])
        unknown = v.difference(['pms', 'portage-1', 'portage-2'])
        if unknown:
            logger.warning("repository at %r has an unsupported profile format: %s" %
                (self.location, ', '.join(repr(x) for x in sorted(v))))
            v = 'pms'
        sf(self, 'profile_format', list(v)[0])

    @klass.jit_attr
    def raw_known_arches(self):
        try:
            return frozenset(iter_read_bash(
                pjoin(self.profiles_base, 'arch.list')))
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
            return frozenset()

    @klass.jit_attr
    def raw_use_desc(self):
        # todo: convert this to using a common exception base, with
        # conversion of ValueErrors...
        def converter(key):
            return (packages.AlwaysTrue, key)
        return tuple(self._split_use_desc_file('use.desc', converter))

    @klass.jit_attr
    def raw_use_local_desc(self):
        def converter(key):
            # todo: convert this to using a common exception base, with
            # conversion of ValueErrors/atom exceptoins...
            chunks = key.split(':', 1)
            return (atom.atom(chunks[0]), chunks[1])

        return tuple(self._split_use_desc_file('use.local.desc', converter))

    @klass.jit_attr
    def raw_use_expand_desc(self):
        base = pjoin(self.profiles_base, 'desc')
        try:
            targets = sorted(listdir_files(base))
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
            return ()

        def f():
            for use_group in targets:
                group = use_group.split('.', 1)[0] + "_"
                def converter(key):
                    return (packages.AlwaysTrue, group + key)
                for blah in self._split_use_desc_file('desc/%s' % use_group, converter):
                    yield blah
        return tuple(f())

    def _split_use_desc_file(self, name, converter):
        line = None
        fp = pjoin(self.profiles_base, name)
        try:
            for line in iter_read_bash(fp):
                key, val = line.split(None, 1)
                key = converter(key)
                yield key[0], (key[1], val.split('-', 1)[1].strip())
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
        except ValueError as v:
            if line is None:
                raise
            compatibility.raise_from(
                ValueError("Failed parsing %r: line was %r" % (fp, line)))

    known_arches = klass.alias_attr('raw_known_arches')
    use_desc = klass.alias_attr('raw_use_desc')
    use_local_desc = klass.alias_attr('raw_use_local_desc')
    use_expand_desc = klass.alias_attr('raw_use_expand_desc')

    @klass.jit_attr
    def is_empty(self):
        result = True
        try:
            # any files existing means it's not empty
            result = not listdir(self.location)
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise

        if result:
            logger.debug("repository at %r is empty" % (self.location,))
        return result

    @klass.jit_attr
    def repo_id(self):
        val = readfile(pjoin(self.profiles_base, 'repo_name'), True)
        if val is None:
            if not self.is_empty:
                logger.warning("repository at location %r lacks a defined repo_name",
                    self.location)
            val = '<unlabeled repository %s>' % self.location
        return val.strip()

    arch_profiles = klass.alias_attr('profiles.arch_profiles')

    @klass.jit_attr
    def profiles(self):
        return BundledProfiles(self.profiles_base)
