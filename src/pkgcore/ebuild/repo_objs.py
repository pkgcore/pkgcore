# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
package class for buildable ebuilds
"""

__all__ = (
    "Maintainer", "MetadataXml", "LocalMetadataXml",
    "SharedPkgData", "Licenses", "OverlayedLicenses"
)

from itertools import chain

from snakeoil import compatibility, klass, mappings
from snakeoil.caching import WeakInstMeta
from snakeoil.currying import post_curry
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin, listdir_files, listdir
from snakeoil.sequences import namedtuple

from pkgcore.config import ConfigHint
from pkgcore.repository import syncable

demandload(
    'errno',
    'os',
    'snakeoil.bash:BashParseError,iter_read_bash,read_dict',
    'snakeoil.fileutils:readfile,readlines_ascii',
    'snakeoil.sequences:iter_stable_unique',
    'snakeoil.strings:pluralism',
    'snakeoil.xml:etree',
    'pkgcore.ebuild:atom,profiles,pkg_updates',
    'pkgcore.log:logger',
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

    Attributes are set to -1 if unloaded, None if no entry, or the value
    if loaded.
    """

    __slots__ = (
        "__weakref__", "_maintainers", "_local_use",
        "_longdescription", "_source",
    )

    def __init__(self, source):
        self._source = source

    def _generic_attr(self, attr):
        if self._source is not None:
            self._parse_xml()
        return getattr(self, attr)

    for attr in ("maintainers", "local_use", "longdescription"):
        locals()[attr] = property(post_curry(_generic_attr, "_" + attr))
    del attr

    def _parse_xml(self, source=None):
        if source is None:
            source = self._source.bytes_fileobj()
        tree = etree.parse(source)

        # TODO: handle i18n properly
        maintainers = []
        for x in tree.findall("maintainer"):
            name = email = description = None
            for e in x:
                if e.tag == "name":
                    name = e.text
                elif e.tag == "email":
                    email = e.text
                elif e.tag == 'description' and e.get('lang', 'en') == 'en':
                    description = e.text
            maintainers.append(Maintainer(
                name=name, email=email, description=description))

        self._maintainers = tuple(maintainers)

        # Could be unicode!
        self._longdescription = None
        for x in tree.findall("longdescription"):
            if x.get('lang', 'en') != 'en':
                continue
            longdesc = x.text
            if longdesc:
                self._longdescription = ' '.join(longdesc.split())
            break

        self._source = None

        # lang="" is property of <use/>
        self._local_use = mappings.ImmutableDict()
        for x in tree.findall("use"):
            if x.get('lang', 'en') != 'en':
                continue
            self._local_use = mappings.ImmutableDict(
                (e.attrib['name'], ' '.join(''.join(e.itertext()).split()))
                for e in x.findall('flag')
                if 'name' in e.attrib
            )
            break


class LocalMetadataXml(MetadataXml):

    __slots__ = ()

    def _parse_xml(self):
        try:
            MetadataXml._parse_xml(self, open(self._source, "rb", 32768))
        except EnvironmentError as oe:
            if oe.errno != errno.ENOENT:
                raise
            self._maintainers = ()
            self._local_use = mappings.ImmutableDict()
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

    def __init__(self, repo_base, profile_base='profiles',
                 licenses_dir='licenses', license_groups='profiles/license_groups'):
        object.__setattr__(self, '_base', repo_base)
        object.__setattr__(self, 'license_groups_path', pjoin(repo_base, license_groups))
        object.__setattr__(self, 'licenses_dir', pjoin(repo_base, licenses_dir))

    @klass.jit_attr_none
    def licenses(self):
        """Return the set of all defined licenses in a repo."""
        try:
            content = listdir_files(self.licenses_dir)
        except EnvironmentError:
            content = ()
        return frozenset(content)

    @klass.jit_attr_none
    def groups(self):
        """Return the mapping of defined license groups to licenses for a repo."""
        try:
            d = read_dict(self.license_groups_path, splitter=' ')
        except EnvironmentError:
            return mappings.ImmutableDict()
        except BashParseError as pe:
            logger.error("failed parsing license_groups: %s", pe)
            return mappings.ImmutableDict()
        self._expand_groups(d)
        return mappings.ImmutableDict((k, tuple(v)) for (k, v) in d.iteritems())

    def _expand_groups(self, groups):
        keep_going = True
        for k, v in groups.iteritems():
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
                            logger.error(
                                "invalid license group reference: %r in %s", v2, self)
                            continue
                        elif v2 == k:
                            logger.error(
                                "cyclic license group references for %r in %s", v2, self)
                            continue
                        l.extend(groups[v2])
                    else:
                        l.append(v2)
                groups[k] = l

    def refresh(self):
        self._licenses = None
        self._groups = None

    def __getitem__(self, license):
        if license not in self:
            raise KeyError(license)
        try:
            return open(pjoin(self.licenses_dir, license)).read()
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                raise KeyError(license)
            raise

    def __len__(self):
        return len(self.licenses)

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
            for k, v in li.groups.iteritems():
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
        object.__setattr__(self, '_license_instances', tuple(l))


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
        """Return the mapping of arches to profiles for a repo."""
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

    def arches(self, status=None):
        """All arches with profiles defined in the repo."""
        arches = []
        for arch, profiles in self.arch_profiles.iteritems():
            for _profile_path, profile_status in profiles:
                if status is None or profile_status == status:
                    arches.append(arch)
        return frozenset(arches)

    def paths(self, status=None):
        """Yield profile paths optionally matching a given status."""
        if status == 'deprecated':
            for root, dirs, files in os.walk(self.profile_base):
                if os.path.exists(pjoin(root, 'deprecated')):
                    yield root[len(self.profile_base) + 1:]
        else:
            for profile_path, profile_status in chain.from_iterable(self.arch_profiles.itervalues()):
                if status is None or status == profile_status:
                    yield profile_path

    def create_profile(self, node):
        """Return profile object for a given path."""
        return profiles.OnDiskProfile(self.profile_base, node)


class RepoConfig(syncable.tree):

    layout_offset = "metadata/layout.conf"

    default_hashes = ('size', 'sha256', 'sha512', 'whirlpool')
    supported_profile_formats = ('pms', 'portage-1', 'portage-2', 'profile-set')
    supported_cache_formats = ('pms', 'md5-dict')

    klass.inject_immutable_instance(locals())

    __metaclass__ = WeakInstMeta
    __inst_caching__ = True

    pkgcore_config_type = ConfigHint(
        typename='repo_config',
        types={
            'config_name': 'str',
            'syncer': 'lazy_ref:syncer',
        })

    def __init__(self, location, config_name=None, syncer=None, profiles_base='profiles'):
        object.__setattr__(self, 'config_name', config_name)
        object.__setattr__(self, 'location', location)
        object.__setattr__(self, 'profiles_base', pjoin(self.location, profiles_base))
        syncable.tree.__init__(self, syncer)
        self._parse_config()

    def _parse_config(self):
        """Load data from the repo's metadata/layout.conf file."""
        path = pjoin(self.location, self.layout_offset)
        data = read_dict(
            iter_read_bash(readlines_ascii(path, True, True)),
            source_isiter=True, strip=True, filename=path)

        sf = object.__setattr__

        hashes = data.get('manifest-hashes', '').lower().split()
        if hashes:
            hashes = ['size'] + hashes
            hashes = tuple(iter_stable_unique(hashes))
        else:
            hashes = self.default_hashes

        manifest_policy = data.get('use-manifests', 'strict').lower()
        d = {
            'disabled': (manifest_policy == 'false'),
            'strict': (manifest_policy == 'strict'),
            'thin': (data.get('thin-manifests', '').lower() == 'true'),
            'signed': (data.get('sign-manifests', 'true').lower() == 'true'),
            'hashes': hashes,
        }

        # complain if profiles/repo_name is missing
        repo_name = readfile(pjoin(self.profiles_base, 'repo_name'), True)
        if repo_name is None:
            if not self.is_empty:
                logger.warning("repo lacks a defined name: %r", self.location)
            repo_name = '<unlabeled repo %s>' % self.location
        # repo-name setting from metadata/layout.conf overrides profiles/repo_name if it exists
        sf(self, 'repo_name', data.get('repo-name', repo_name.strip()))

        sf(self, 'manifests', _immutable_attr_dict(d))
        masters = data.get('masters')
        if masters is None:
            if not self.is_empty:
                logger.warning(
                    "repo at %r, named %r, doesn't specify masters in metadata/layout.conf. "
                    "Please explicitly set masters (use \"masters =\" if the repo "
                    "is standalone).", self.location, self.repo_id)
            masters = ()
        else:
            masters = tuple(iter_stable_unique(masters.split()))
        sf(self, 'masters', masters)
        aliases = data.get('aliases', '').split() + [self.repo_id, self.location]
        sf(self, 'aliases', tuple(iter_stable_unique(aliases)))
        sf(self, 'eapis_deprecated', tuple(iter_stable_unique(data.get('eapis-deprecated', '').split())))

        v = set(data.get('cache-formats', 'pms').lower().split())
        if not v:
            v = [None]
        elif not v.intersection(self.supported_cache_formats):
            v = ['pms']
        sf(self, 'cache_format', list(v)[0])

        profile_formats = set(data.get('profile-formats', 'pms').lower().split())
        if not profile_formats:
            logger.warning(
                "%r repo at %r has explicitly unset profile-formats, "
                "defaulting to pms", self.repo_id, self.location)
            profile_formats = set(['pms'])
        unknown = profile_formats.difference(self.supported_profile_formats)
        if unknown:
            logger.warning(
                "%r repo at %r has unsupported profile format%s: %s",
                self.repo_id, self.location, pluralism(unknown),
                ', '.join(sorted(unknown)))
            profile_formats.difference_update(unknown)
            profile_formats.add('pms')
        sf(self, 'profile_formats', profile_formats)

    @klass.jit_attr
    def raw_known_arches(self):
        """All valid KEYWORDS for the repo."""
        try:
            return frozenset(iter_read_bash(
                pjoin(self.profiles_base, 'arch.list')))
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise
            return frozenset()

    @klass.jit_attr
    def raw_use_desc(self):
        """Global USE flags for the repo."""
        # todo: convert this to using a common exception base, with
        # conversion of ValueErrors...
        def converter(key):
            return (packages.AlwaysTrue, key)
        return tuple(self._split_use_desc_file('use.desc', converter))

    @klass.jit_attr
    def raw_use_local_desc(self):
        """Local USE flags for the repo."""
        def converter(key):
            # todo: convert this to using a common exception base, with
            # conversion of ValueErrors/atom exceptions...
            chunks = key.split(':', 1)
            return (atom.atom(chunks[0]), chunks[1])

        return tuple(self._split_use_desc_file('use.local.desc', converter))

    @klass.jit_attr
    def raw_use_expand_desc(self):
        """USE_EXPAND settings for the repo."""
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

                for x in self._split_use_desc_file('desc/%s' % use_group, converter):
                    yield x

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
        except ValueError:
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
        """Return boolean related to if the repo has files in it."""
        result = True
        try:
            # any files existing means it's not empty
            result = not listdir(self.location)
        except EnvironmentError as e:
            if e.errno != errno.ENOENT:
                raise

        if result:
            logger.debug("repo is empty: %r", self.location)
        return result

    @klass.jit_attr
    def repo_id(self):
        """Main identifier for the repo.

        The name set in repos.conf for a repo overrides any repo-name settings
        in the repo.
        """
        if self.config_name is not None:
            return self.config_name
        return self.repo_name

    @klass.jit_attr
    def updates(self):
        """Package updates for the repo defined in profiles/updates/*."""
        d = {}
        updates_dir = pjoin(self.profiles_base, 'updates')
        if os.path.exists(updates_dir):
            d = pkg_updates.read_updates(updates_dir)
        return mappings.ImmutableDict(d)

    @klass.jit_attr
    def profiles(self):
        return BundledProfiles(self.profiles_base)

    arch_profiles = klass.alias_attr('profiles.arch_profiles')
