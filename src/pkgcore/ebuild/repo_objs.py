# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
package class for buildable ebuilds
"""

__all__ = (
    "Maintainer", "MetadataXml", "LocalMetadataXml",
    "SharedPkgData", "Licenses", "OverlayedLicenses"
)

from collections import namedtuple
import errno
from itertools import chain

from snakeoil import klass, mappings
from snakeoil.caching import WeakInstMeta
from snakeoil.currying import post_curry
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin, listdir_files, listdir
from snakeoil.osutils.mount import mount, umount

from pkgcore.config import ConfigHint
from pkgcore.exceptions import PermissionDenied
from pkgcore.repository import syncable, errors as repo_errors

demandload(
    'lxml:etree',
    'os',
    'platform',
    'subprocess',
    'snakeoil.bash:BashParseError,iter_read_bash,read_dict',
    'snakeoil.fileutils:readfile,readlines_ascii',
    'snakeoil.process.namespaces:simple_unshare',
    'snakeoil.sequences:iter_stable_unique',
    'snakeoil.strings:pluralism',
    'pkgcore.ebuild:atom,profiles,pkg_updates',
    'pkgcore.ebuild.eapi:get_eapi',
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
                res = f'{self.name} <{self.email}>'
            else:
                res = self.name
        else:
            res = self.email
        if self.description is not None:
            return '{res} ({self.description})'
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
        except FileNotFoundError:
            self._maintainers = ()
            self._local_use = mappings.ImmutableDict()
            self._longdescription = None
            self._source = None


class SharedPkgData(object):

    __slots__ = ("__weakref__", "metadata_xml", "manifest")

    def __init__(self, metadata_xml, manifest):
        self.metadata_xml = metadata_xml
        self.manifest = manifest


class Licenses(object, metaclass=WeakInstMeta):

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
            logger.error(f"failed parsing license_groups: {pe}")
            return mappings.ImmutableDict()
        self._expand_groups(d)
        return mappings.ImmutableDict((k, tuple(v)) for (k, v) in d.items())

    def _expand_groups(self, groups):
        keep_going = True
        for k, v in groups.items():
            groups[k] = v.split()
        while keep_going:
            keep_going = False
            for k, v in groups.items():
                if not any(x[0] == '@' for x in v):
                    continue
                keep_going = True
                l = []
                for v2 in v:
                    if v2[0] == '@':
                        v2 = v2[1:]
                        if not v2 or v2 not in groups:
                            logger.error(
                                f"invalid license group reference: {v2!r} in {self}")
                            continue
                        elif v2 == k:
                            logger.error(
                                f"cyclic license group references for {v2!r} in {self}")
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
        except FileNotFoundError:
            raise KeyError(license)

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
            for k, v in li.groups.items():
                if k in d:
                    d[k] += v
                else:
                    d[k] = v
        return d

    @klass.jit_attr_none
    def licenses(self):
        return frozenset(chain.from_iterable(self._license_instances))

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
                        f"{fp}: line doesn't follow 'key profile status' form: {line}")
                    continue
                # Normalize the profile name on the offchance someone slipped an extra /
                # into it.
                d[key].append(_KnownProfile(
                    '/'.join(filter(None, profile.split('/'))), status))
        except FileNotFoundError:
            logger.debug(f"No profile descriptions found at {fp!r}")
        return mappings.ImmutableDict(
            (k, tuple(sorted(v))) for k, v in d.items())

    def arches(self, status=None):
        """All arches with profiles defined in the repo."""
        arches = []
        for arch, profiles in self.arch_profiles.items():
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
            for profile_path, profile_status in chain.from_iterable(self.arch_profiles.values()):
                if status is None or status == profile_status:
                    yield profile_path

    def create_profile(self, node):
        """Return profile object for a given path."""
        return profiles.OnDiskProfile(self.profile_base, node)


class RepoConfig(syncable.tree, metaclass=WeakInstMeta):
    """Configuration data for an ebuild repository."""

    layout_offset = "metadata/layout.conf"

    default_hashes = ('size', 'blake2b', 'sha512')
    default_required_hashes = ('size', 'blake2b')
    supported_profile_formats = ('pms', 'portage-1', 'portage-2', 'profile-set')
    supported_cache_formats = ('pms', 'md5-dict')

    klass.inject_immutable_instance(locals())
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

        if not self.eapi.is_supported:
            raise repo_errors.UnsupportedRepo(self)

        super().__init__(syncer)
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

        required_hashes = data.get('manifest-required-hashes', '').lower().split()
        if required_hashes:
            required_hashes = ['size'] + required_hashes
            required_hashes = tuple(iter_stable_unique(required_hashes))
        else:
            required_hashes = self.default_required_hashes

        manifest_policy = data.get('use-manifests', 'strict').lower()
        d = {
            'disabled': (manifest_policy == 'false'),
            'strict': (manifest_policy == 'strict'),
            'thin': (data.get('thin-manifests', '').lower() == 'true'),
            'signed': (data.get('sign-manifests', 'true').lower() == 'true'),
            'hashes': hashes,
            'required_hashes': required_hashes,
        }

        # complain if profiles/repo_name is missing
        repo_name = readfile(pjoin(self.profiles_base, 'repo_name'), True)
        if repo_name is None:
            if not self.is_empty:
                logger.warning(f"repo lacks a defined name: {self.location!r}")
            repo_name = f'<unlabeled repo {self.location}>'
        # repo-name setting from metadata/layout.conf overrides profiles/repo_name if it exists
        sf(self, 'repo_name', data.get('repo-name', repo_name.strip()))

        sf(self, 'manifests', _immutable_attr_dict(d))
        masters = data.get('masters')
        if masters is None:
            if not self.is_empty:
                logger.warning(
                    f"repo at {self.location!r}, named {self.repo_id!r}, doesn't "
                    "specify masters in metadata/layout.conf. Please explicitly "
                    "set masters (use \"masters =\" if the repo is standalone).")
            masters = ()
        else:
            masters = tuple(iter_stable_unique(masters.split()))
        sf(self, 'masters', masters)
        aliases = data.get('aliases', '').split() + [self.repo_id, self.location]
        sf(self, 'aliases', tuple(iter_stable_unique(aliases)))
        sf(self, 'eapis_deprecated', tuple(iter_stable_unique(data.get('eapis-deprecated', '').split())))
        sf(self, 'eapis_banned', tuple(iter_stable_unique(data.get('eapis-banned', '').split())))

        v = set(data.get('cache-formats', 'pms').lower().split())
        if not v:
            v = [None]
        elif not v.intersection(self.supported_cache_formats):
            v = ['pms']
        sf(self, 'cache_format', list(v)[0])

        profile_formats = set(data.get('profile-formats', 'pms').lower().split())
        if not profile_formats:
            logger.warning(
                f"{self.repo_id!r} repo at {self.location!r} has explicitly "
                "unset profile-formats, defaulting to pms")
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
        except FileNotFoundError:
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
        except FileNotFoundError:
            return ()

        def f():
            for use_group in targets:
                group = use_group.split('.', 1)[0] + "_"

                def converter(key):
                    return (packages.AlwaysTrue, group + key)

                for x in self._split_use_desc_file(f'desc/{use_group}', converter):
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
        except FileNotFoundError:
            pass
        except ValueError as e:
            if line is None:
                raise
            raise ValueError(f"Failed parsing {fp!r}: line was {line!r}") from e

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
        except FileNotFoundError:
            pass

        if result:
            logger.debug(f"repo is empty: {self.location!r}")
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

    @klass.jit_attr
    def eapi(self):
        try:
            path = pjoin(self.profiles_base, 'eapi')
            data = [x.strip() for x in iter_read_bash(path)]
            data = [_f for _f in data if _f]
            if len(data) != 1:
                raise ValueError(f"multiple lines detected: {path!r}")
            return get_eapi(data[0])
        except FileNotFoundError:
            return get_eapi('0')


class SquashfsRepoConfig(RepoConfig):
    """Configuration data for an ebuild repository in a squashfs archive.

    Linux only support for transparently supporting ebuild repos compressed
    into squashfs archives.
    """

    def __init__(self, sqfs_file, location, *args, **kwargs):
        sqfs_path = pjoin(location, sqfs_file)
        object.__setattr__(self, '_sqfs', sqfs_path)
        object.__setattr__(self, 'location', location)
        # if squashfs archive exists in the repo, try to mount it over itself
        if os.path.exists(self._sqfs):
            try:
                self._mount_archive()
            except PermissionError as e:
                if platform.uname().release < '4.18':
                    raise repo_errors.InitializationError(
                        'fuse mounts in user namespaces require linux >= 4.18')
                raise
        super().__init__(location, *args, **kwargs)

    def _pre_sync(self):
        try:
            self._umount_archive()
        except repo_errors.InitializationError:
            pass

    def _post_sync(self):
        if os.path.exists(self._sqfs):
            self._mount_archive()

    def _failed_cmd(self, ret, action):
        if ret.returncode:
            stderr = ret.stderr.decode().strip().lower()
            msg = f'failed {action} squashfs archive: {stderr}'
            if ret.returncode == 1:
                raise PermissionDenied(self._sqfs, msg)
            else:
                raise repo_errors.InitializationError(msg)

    def _mount_archive(self):
        """Mount the squashfs archive onto the repo in a mount namespace."""
        # enable a user namespace if not running as root
        unshare_kwds = {'mount': True, 'user': not os.getuid() == 0}
        try:
            simple_unshare(**unshare_kwds)
        except OSError as e:
            raise repo_errors.InitializationError(
                f'namespace support unavailable: {e.strerror}')

        # First try using mount to automatically handle setting up loop device
        # -- this only works with real root perms since loopback device
        # mounting (losetup) doesn't work in user namespaces.
        try:
            mount(self._sqfs, self.location, 'squashfs', 0)
            return
        except FileNotFoundError as e:
            raise repo_errors.InitializationError(
                f'failed mounting squashfs archive: {e.filename} required')
        except OSError as e:
            # fail out if not a permissions issue (regular or loopback failure inside userns)
            if e.errno not in (errno.EPERM, errno.EPIPE):
                raise repo_errors.InitializationError(
                    f'failed mounting squashfs archive: {e.strerror}')

        # fallback to using squashfuse
        try:
            # TODO: switch to capture_output=True when >= py3.7
            ret = subprocess.run(
                ['squashfuse', '-o', 'nonempty', self._sqfs, self.location],
                stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        except FileNotFoundError as e:
            raise repo_errors.InitializationError(
                f'failed mounting squashfs archive: {e.filename} required')

        if ret.returncode:
            self._failed_cmd(ret, 'mounting')

    def _umount_archive(self):
        """Unmount the squashfs archive."""
        try:
            umount(self.location)
            return
        except FileNotFoundError as e:
            raise repo_errors.InitializationError(
                f'failed unmounting squashfs archive: {e.filename} required')
        except OSError as e:
            # fail out if not a permissions issue (regular or loopback failure inside userns)
            if e.errno not in (errno.EPERM, errno.EPIPE):
                raise repo_errors.InitializationError(
                    f'failed unmounting squashfs archive: {e.strerror}')

        # fallback to using fusermount
        try:
            # TODO: switch to capture_output=True when >= py3.7
            ret = subprocess.run(
                ['fusermount', '-u', self.location],
                stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        except FileNotFoundError as e:
            raise repo_errors.InitializationError(
                f'failed unmounting squashfs archive: {e.filename} required')

        if ret.returncode:
            self._failed_cmd(ret, 'unmounting')
