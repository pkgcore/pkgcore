"""
package class for buildable ebuilds
"""

__all__ = (
    "Maintainer", "MetadataXml", "LocalMetadataXml",
    "SharedPkgData", "Licenses", "OverlayedLicenses", "OverlayedProfiles",
    "Project", "ProjectMember", "Subproject", "ProjectsXml", "LocalProjectsXml"
)

import errno
import os
import platform
import subprocess
from collections import namedtuple
from itertools import chain
from sys import intern

from lxml import etree
from snakeoil import klass, mappings
from snakeoil.bash import BashParseError, iter_read_bash, read_dict
from snakeoil.caching import WeakInstMeta
from snakeoil.currying import post_curry
from snakeoil.fileutils import readfile, readlines
from snakeoil.osutils import listdir, listdir_files, pjoin
from snakeoil.osutils.mount import umount
from snakeoil.process.namespaces import simple_unshare
from snakeoil.sequences import iter_stable_unique
from snakeoil.strings import pluralism

from ..config.hint import ConfigHint
from ..exceptions import PermissionDenied
from ..log import logger
from ..repository import errors as repo_errors
from ..repository import syncable
from ..restrictions import packages
from . import atom, pkg_updates, profiles
from .eapi import get_eapi


class Maintainer:
    """Data on a single maintainer.

    At least one of email and name is not C{None}.

    :type email: C{unicode} object or C{None}
    :ivar email: email address.
    :type name: C{unicode} object or C{None}
    :ivar name: full name
    :type description: C{unicode} object or C{None}
    :ivar description: description of maintainership.
    :type maint_type: C{unicode} object or C{None}
    :ivar maint_type: maintainer type (person or project).
    """

    __slots__ = ('email', 'description', 'name', 'maint_type')

    def __init__(self, email=None, name=None, description=None, maint_type=None):
        if email is None and name is None:
            raise ValueError('need at least one of name and email')
        self.email = email
        self.name = name
        self.description = description
        self.maint_type = maint_type

    def __str__(self):
        if self.name is not None:
            if self.email is not None:
                res = f'{self.name} <{self.email}>'
            else:
                res = self.name
        else:
            res = self.email
        if self.description is not None:
            return f'{res} ({self.description})'
        return res

    def __eq__(self, other):
        try:
            return self.email == other.email and self.name == other.name
        except AttributeError:
            if isinstance(other, str):
                return other == self.email or other == self.name
        return False


class MetadataXml:
    """metadata.xml parsed results

    Attributes are set to -1 if unloaded, None if no entry, or the value
    if loaded.
    """

    __slots__ = (
        "__weakref__", "_maintainers", "_local_use",
        "_longdescription", "_source", "_stabilize_allarches",
    )

    def __init__(self, source):
        self._source = source

    def _generic_attr(self, attr):
        if self._source is not None:
            self._parse_xml()
        return getattr(self, attr)

    for attr in ("maintainers", "local_use", "longdescription",
                 "stabilize_allarches"):
        locals()[attr] = property(post_curry(_generic_attr, "_" + attr))
    del attr

    def _parse_xml(self, source=None):
        if source is None:
            source = self._source.bytes_fileobj()
        try:
            tree = etree.parse(source)
        except etree.XMLSyntaxError as e:
            self._maintainers = ()
            self._local_use = mappings.ImmutableDict()
            self._longdescription = None
            self._source = None
            self._stabilize_allarches = False
            logger.error(e)
            return

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
            try:
                maintainers.append(Maintainer(
                    name=name, email=email, description=description,
                    maint_type=x.get('type')))
            except ValueError:
                # ignore invalid maintainers that should be caught by pkgcheck
                pass

        self._maintainers = tuple(maintainers)

        # Could be unicode!
        self._longdescription = None
        for x in tree.findall("longdescription"):
            if x.get('lang', 'en') != 'en':
                continue
            longdesc = ''.join(x.itertext())
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

        self._stabilize_allarches = tree.find("stabilize-allarches") is not None


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
            self._stabilize_allarches = False


class SharedPkgData:

    __slots__ = ("__weakref__", "metadata_xml", "manifest")

    def __init__(self, metadata_xml, manifest):
        self.metadata_xml = metadata_xml
        self.manifest = manifest


class ProjectMember(metaclass=klass.generic_equality):
    """Data on a single project member.

    :type email: C{unicode} object
    :ivar email: email address.
    :type name: C{unicode} object or C{None}
    :ivar name: full name
    :type role: C{unicode} object or C{None}
    :ivar role: role within the project.
    :type is_lead: C{bool}
    :ivar is_lead: whether the member is a project lead.
    """

    __slots__ = ('email', 'name', 'role', 'is_lead')
    __attr_comparison__ = ('email', 'name', 'role', 'is_lead')

    def __init__(self, email, name=None, role=None, is_lead=None):
        if email is None:
            raise ValueError('email for project member must not be null')
        self.email = email
        self.name = name
        self.role = role
        self.is_lead = is_lead

    def __str__(self):
        if self.name is not None:
            res = f'{self.name} <{self.email}>'
        else:
            res = self.email
        if self.role is not None:
            return f'{res} ({self.role})'
        return res


class Subproject:
    """Data on a subproject.

    :type inherit_members: C{bool}
    :ivar inherit_members: whether the parent project inherits members from this subproject
    """

    __slots__ = ('_ref', 'inherit_members', '_projects_xml', '_project')

    def __init__(self, ref, projects_xml, inherit_members=None):
        if ref is None:
            raise ValueError('ref for subproject must not be null')
        self._ref = ref
        self.inherit_members = inherit_members
        self._projects_xml = projects_xml

    @klass.jit_attr
    def project(self):
        try:
            return self._projects_xml.projects[self._ref]
        except KeyError:
            logger.error(f'projects.xml: subproject {self._ref!r} does not exist')
            return None

    __getattr__ = klass.GetAttrProxy('project')
    __dir__ = klass.DirProxy('project')


class Project:
    """Data on a single project.

    :type email: C{unicode} object
    :ivar email: email address.
    :type name: C{unicode} object or C{None}
    :ivar name: full name
    :type url: C{unicode} object or C{None}
    :ivar url: project website URI
    :type description: C{unicode} object or C{None}
    :ivar description: full project description.
    :type members: C{tuple} of C{ProjectMember}
    :ivar members: project members
    :type subprojects: C{tuple} of C{Subprojects}
    :ivar subprojects: subprojects
    """

    __slots__ = ('email', 'name', 'url', 'description', 'members', 'subprojects')

    def __init__(self, email, name=None, url=None, description=None,
                 members=(), subprojects=()):
        if email is None:
            raise ValueError('email for project must not be null')
        self.email = email
        self.name = name
        self.url = url
        self.description = description
        self.members = tuple(members)
        self.subprojects = tuple(subprojects)

    def __str__(self):
        if self.name is not None:
            res = f'{self.name} <{self.email}>'
        else:
            res = self.email
        if self.url is not None:
            return f'{res} ({self.url})'
        return res

    @property
    def leads(self):
        """Project lead(s), if any."""
        return tuple(m for m in self.members if m.is_lead)

    @property
    def recursive_members(self):
        """All project members, including members inherited from subprojects."""
        subprojects = list(
            sp for sp in self.subprojects
            if sp.inherit_members and sp.project is not None)
        subproject_emails = set(sp.email for sp in subprojects)

        # recursively collect all subprojects from which to inherit
        i = 0
        while i < len(subprojects):
            for sp in subprojects[i].subprojects:
                if sp.project is None:
                    continue
                if sp.inherit_members and sp.email not in subproject_emails:
                    subprojects.append(sp)
                    subproject_emails.add(sp.email)
            i += 1

        members = {m.email: m for m in self.members}
        for sp in (x for x in subprojects if x.inherit_members):
            for m in sp.members:
                if m.email not in members:
                    # drop lead bit
                    m = ProjectMember(
                        email=m.email, name=m.name, role=m.role, is_lead=False)
                    members[m.email] = m
        return tuple(members.values())


class ProjectsXml:
    """projects.xml parsed results

    Attributes are set to -1 if unloaded, None if no entry, or the value
    if loaded.
    """

    __slots__ = ('__weakref__', '_projects', '_source')

    def __init__(self, source):
        self._source = source

    @klass.jit_attr
    def projects(self):
        if self._source is not None:
            return self._parse_xml()
        return mappings.ImmutableDict()

    def _parse_xml(self, source=None):
        if source is None:
            source = self._source.bytes_fileobj()
        try:
            tree = etree.parse(source)
        except etree.XMLSyntaxError as e:
            logger.error(f'failed parsing projects.xml: {e}')
            return mappings.ImmutableDict()

        projects = {}
        for p in tree.findall('project'):
            kwargs = {}
            for k in ('email', 'name', 'url', 'description'):
                kwargs[k] = p.findtext(k)

            members = []
            for m in p.findall('member'):
                m_kwargs = {}
                for k in ('email', 'name', 'role'):
                    m_kwargs[k] = m.findtext(k)
                m_kwargs['is_lead'] = m.get('is-lead', '') == '1'
                try:
                    members.append(ProjectMember(**m_kwargs))
                except ValueError:
                    logger.error(f"project {kwargs['email']} has <member/> with no email")
            kwargs['members'] = members

            subprojects = []
            for sp in p.findall('subproject'):
                try:
                    subprojects.append(Subproject(
                        ref=sp.get('ref'),
                        inherit_members=sp.get('inherit-members', '') == '1',
                        projects_xml=self))
                except ValueError:
                    logger.error(f"project {kwargs['email']} has <subproject/> with no ref")
            kwargs['subprojects'] = subprojects

            projects[kwargs['email']] = Project(**kwargs)

        return mappings.ImmutableDict(projects)


class LocalProjectsXml(ProjectsXml):

    __slots__ = ()

    def _parse_xml(self):
        try:
            with open(self._source, "rb", 32768) as f:
                return super()._parse_xml(f)
        except FileNotFoundError:
            return mappings.ImmutableDict()


class Licenses(metaclass=WeakInstMeta):

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
        return mappings.ImmutableDict((k, frozenset(v)) for (k, v) in d.items())

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
                    d[k] |= v
                else:
                    d[k] = v
        return mappings.ImmutableDict(d)

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


_KnownProfile = namedtuple('_KnownProfile', ['base', 'arch', 'path', 'status', 'deprecated'])


class Profiles(klass.ImmutableInstance):

    __slots__ = ('config', 'profiles_base', '_profiles')
    __inst_caching__ = True

    def __init__(self, repo_config, profiles_base=None):
        object.__setattr__(self, 'config', repo_config)
        profiles_base = profiles_base if profiles_base is not None else repo_config.profiles_base
        object.__setattr__(self, 'profiles_base', profiles_base)

    @klass.jit_attr_none
    def profiles(self):
        return self.parse(self.profiles_base, self.config.repo_id)

    @staticmethod
    def parse(profiles_base, repo_id, known_status=None, known_arch=None):
        """Return the mapping of arches to profiles for a repo."""
        l = []
        fp = pjoin(profiles_base, 'profiles.desc')
        try:
            for lineno, line in iter_read_bash(fp, enum_line=True):
                try:
                    arch, profile, status = line.split()
                except ValueError:
                    logger.error(
                        f"{repo_id}::profiles/profiles.desc, "
                        f"line {lineno}: invalid profile line format: "
                        "should be 'arch profile status'")
                    continue
                if known_status is not None and status not in known_status:
                    logger.warning(
                        f"{repo_id}::profiles/profiles.desc, "
                        f"line {lineno}: unknown profile status: {status!r}")
                if known_arch is not None and arch not in known_arch:
                    logger.warning(
                        f"{repo_id}::profiles/profiles.desc, "
                        f"line {lineno}: unknown arch: {arch!r}")
                # Normalize the profile name on the offchance someone slipped an extra /
                # into it.
                path = '/'.join(filter(None, profile.split('/')))
                deprecated = os.path.exists(
                    os.path.join(profiles_base, path, 'deprecated'))
                l.append(_KnownProfile(profiles_base, arch, path, status, deprecated))
        except FileNotFoundError:
            # no profiles exist
            pass
        return frozenset(l)

    def __len__(self):
        return len(self.profiles)

    def __iter__(self):
        yield from self.profiles

    def __getitem__(self, path):
        if path[0] == '/':
            path = path.lstrip(self.profiles_base).lstrip(os.sep)
        for p in self.profiles:
            if p.path == path:
                return p
        raise KeyError(path)

    def __contains__(self, path):
        if path[0] == '/':
            path = path.lstrip(self.profiles_base).lstrip(os.sep)
        for p in self.profiles:
            if p.path == path:
                return True
        return False

    def refresh(self):
        self._profiles = None

    def arches(self, status=None):
        """All arches with profiles defined in the repo optionally matching a given status."""
        arches = []
        for p in self.profiles:
            if status is None or status == p.status:
                arches.append(p.arch)
        return frozenset(arches)

    def get_profiles(self, status):
        """Yield profiles matching a given status."""
        for p in self.profiles:
            if status == p.status or (status == 'deprecated' and p.deprecated):
                yield p

    def create_profile(self, node, **kwargs):
        """Return profile object for a given, parsed profile entry."""
        return profiles.OnDiskProfile(node.base, node.path, **kwargs)


class OverlayedProfiles(Profiles):

    __inst_caching__ = True
    __slots__ = ('_profiles_instances', '_profiles_sources')

    def __init__(self, *profiles_sources):
        object.__setattr__(self, '_profiles_sources', profiles_sources)
        self._load_profiles_instances()

    @klass.jit_attr_none
    def profiles(self):
        return frozenset(chain.from_iterable(self._profiles_instances))

    def refresh(self):
        self._load_profiles_instances()
        for pi in self._profiles_instances:
            pi.refresh()
        Profiles.refresh(self)

    def _load_profiles_instances(self):
        l = []
        for x in self._profiles_sources:
            if isinstance(x, Profiles):
                l.append(x)
            elif hasattr(x, 'profiles'):
                l.append(x.profiles)
        object.__setattr__(self, '_profiles_instances', tuple(l))


class RepoConfig(syncable.tree, klass.ImmutableInstance, metaclass=WeakInstMeta):
    """Configuration data for an ebuild repository."""

    layout_offset = "metadata/layout.conf"

    default_hashes = ('size', 'blake2b', 'sha512')
    default_required_hashes = ('size', 'blake2b')
    supported_profile_formats = ('pms', 'portage-1', 'portage-2', 'profile-set')
    supported_cache_formats = ('md5-dict', 'pms')

    __inst_caching__ = True

    pkgcore_config_type = ConfigHint(
        typename='repo_config',
        types={
            'config_name': 'str',
            'syncer': 'lazy_ref:syncer',
        })

    def __init__(self, location, config_name=None, syncer=None, profiles_base='profiles'):
        super().__init__(syncer)
        object.__setattr__(self, 'config_name', config_name)
        object.__setattr__(self, 'location', location)
        object.__setattr__(self, 'profiles_base', pjoin(self.location, profiles_base))

        try:
            self._parse_config()
        except OSError as e:
            raise repo_errors.InitializationError(str(e))

        if not self.eapi.is_supported:
            raise repo_errors.UnsupportedRepo(self)

    def _parse_config(self):
        """Load data from the repo's metadata/layout.conf file."""
        path = pjoin(self.location, self.layout_offset)
        data = read_dict(
            iter_read_bash(readlines(path, strip_whitespace=True, swallow_missing=True)),
            source_isiter=True, strip=True, filename=path, ignore_errors=True)

        sf = object.__setattr__
        sf(self, 'repo_name', data.get('repo-name', None))

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

        sf(self, 'manifests', _immutable_attr_dict(d))
        masters = data.get('masters')
        _missing_masters = False
        if masters is None:
            if not self.is_empty:
                logger.warning(
                    f"{self.repo_id} repo at {self.location!r}, doesn't "
                    "specify masters in metadata/layout.conf. Please explicitly "
                    "set masters (use \"masters =\" if the repo is standalone).")
            _missing_masters = True
            masters = ()
        else:
            masters = tuple(iter_stable_unique(masters.split()))
        sf(self, '_missing_masters', _missing_masters)
        sf(self, 'masters', masters)
        aliases = data.get('aliases', '').split() + [
            self.config_name, self.repo_name, self.pms_repo_name, self.location]
        sf(self, 'aliases', tuple(filter(None, iter_stable_unique(aliases))))
        sf(self, 'eapis_deprecated', tuple(iter_stable_unique(data.get('eapis-deprecated', '').split())))
        sf(self, 'eapis_banned', tuple(iter_stable_unique(data.get('eapis-banned', '').split())))
        sf(self, 'properties_allowed', tuple(iter_stable_unique(data.get('properties-allowed', '').split())))
        sf(self, 'restrict_allowed', tuple(iter_stable_unique(data.get('restrict-allowed', '').split())))

        v = set(data.get('cache-formats', 'md5-dict').lower().split())
        if not v:
            v = [None]
        else:
            # sort into favored order
            v = [f for f in self.supported_cache_formats if f in v]
            if not v:
                logger.warning('unknown cache format: falling back to md5-dict format')
                v = ['md5-dict']
        sf(self, 'cache_format', list(v)[0])

        profile_formats = set(data.get('profile-formats', 'pms').lower().split())
        if not profile_formats:
            logger.info(
                f"{self.repo_id!r} repo at {self.location!r} has explicitly "
                "unset profile-formats, defaulting to pms")
            profile_formats = {'pms'}
        unknown = profile_formats.difference(self.supported_profile_formats)
        if unknown:
            logger.info(
                "%r repo at %r has unsupported profile format%s: %s",
                self.repo_id, self.location, pluralism(unknown),
                ', '.join(sorted(unknown)))
            profile_formats.difference_update(unknown)
            profile_formats.add('pms')
        sf(self, 'profile_formats', profile_formats)

    @klass.jit_attr
    def known_arches(self):
        """All valid KEYWORDS for the repo."""
        try:
            return frozenset(iter_read_bash(
                pjoin(self.profiles_base, 'arch.list')))
        except FileNotFoundError:
            return frozenset()

    @klass.jit_attr
    def arches_desc(self):
        """Arch stability status (GLEP 72).

        See https://www.gentoo.org/glep/glep-0072.html for more details.
        """
        fp = pjoin(self.profiles_base, 'arches.desc')
        d = {'stable': set(), 'transitional': set(), 'testing': set()}
        try:
            for lineno, line in iter_read_bash(fp, enum_line=True):
                try:
                    arch, status = line.split()
                except ValueError:
                    logger.error(
                        f"{self.repo_id}::profiles/arches.desc, "
                        f"line {lineno}: invalid line format: "
                        "should be '<arch> <status>'")
                    continue
                if arch not in self.known_arches:
                    logger.warning(
                        f"{self.repo_id}::profiles/arches.desc, "
                        f"line {lineno}: unknown arch: {arch!r}")
                    continue
                if status not in d:
                    logger.warning(
                        f"{self.repo_id}::profiles/arches.desc, "
                        f"line {lineno}: unknown status: {status!r}")
                    continue
                d[status].add(arch)
        except FileNotFoundError:
            pass
        return mappings.ImmutableDict(d)

    @klass.jit_attr
    def use_desc(self):
        """Global USE flags for the repo."""
        # todo: convert this to using a common exception base, with
        # conversion of ValueErrors...
        def converter(key):
            return (packages.AlwaysTrue, key)
        return tuple(self._split_use_desc_file('use.desc', converter))

    @klass.jit_attr
    def use_local_desc(self):
        """Local USE flags for the repo."""
        def converter(key):
            # todo: convert this to using a common exception base, with
            # conversion of ValueErrors/atom exceptions...
            chunks = key.split(':', 1)
            return (atom.atom(chunks[0]), chunks[1])

        return tuple(self._split_use_desc_file('use.local.desc', converter))

    @klass.jit_attr
    def use_expand_desc(self):
        """USE_EXPAND settings for the repo."""
        base = pjoin(self.profiles_base, 'desc')
        d = dict()
        try:
            targets = listdir_files(base)
        except FileNotFoundError:
            targets = []

        for use_group in targets:
            group = use_group.split('.', 1)[0]
            d[group] = tuple(
                self._split_use_desc_file(
                    f'desc/{use_group}', lambda k: f'{group}_{k}', matcher=False))

        return mappings.ImmutableDict(d)

    def _split_use_desc_file(self, name, converter, matcher=True):
        line = None
        fp = pjoin(self.profiles_base, name)
        try:
            for line in iter_read_bash(fp):
                try:
                    key, val = line.split(None, 1)
                    key = converter(key)
                    if matcher:
                        yield key[0], (key[1], val.split('-', 1)[1].strip())
                    else:
                        yield key, val.split('-', 1)[1].strip()
                except ValueError as e:
                    logger.error(f'failed parsing {fp!r}, line {line!r}: {e}')
        except FileNotFoundError:
            pass
        except ValueError as e:
            logger.error(f'failed parsing {fp!r}: {e}')

    @klass.jit_attr
    def is_empty(self):
        """Return boolean related to if the repo has files in it."""
        result = True
        try:
            # any files existing means it's not empty
            result = not listdir(self.location)
            if result:
                logger.debug(f"repo is empty: {self.location!r}")
        except FileNotFoundError:
            pass

        return result

    @klass.jit_attr
    def pms_repo_name(self):
        """Repository name from profiles/repo_name (as defined by PMS).

        We're more lenient than the spec and don't verify it conforms to the
        specified format.
        """
        name = readfile(pjoin(self.profiles_base, 'repo_name'), none_on_missing=True)
        if name is not None:
            name = name.split('\n', 1)[0].strip()
        return name

    @klass.jit_attr
    def repo_id(self):
        """Main identifier for the repo.

        The precedence order is as follows: repos.conf name, repo-name from
        metadata/layout.conf, profiles/repo_name, and finally a fallback to the
        repo's location for unlabeled repos.
        """
        if self.config_name:
            return self.config_name
        # repo_name might not be parsed yet if failure occurs during init
        if repo_name := getattr(self, 'repo_name', None):
            return repo_name
        if self.pms_repo_name:
            return self.pms_repo_name
        if not self.is_empty:
            logger.warning(f"repo lacks a defined name: {self.location!r}")
        return self.location

    @klass.jit_attr
    def updates(self):
        """Package updates for the repo defined in profiles/updates/*."""
        updates_dir = pjoin(self.profiles_base, 'updates')
        d = pkg_updates.read_updates(updates_dir)
        return mappings.ImmutableDict(d)

    @klass.jit_attr
    def categories(self):
        categories = readlines(pjoin(self.profiles_base, 'categories'), True, True, True)
        if categories is not None:
            return tuple(map(intern, categories))
        return ()

    @klass.jit_attr
    def profiles(self):
        return Profiles(self)

    @klass.jit_attr
    def base_profile(self):
        pms_strict = 'pms' in self.profile_formats
        return profiles.EmptyRootNode(self.profiles_base, pms_strict=pms_strict)

    @klass.jit_attr
    def eapi(self):
        try:
            return self.base_profile.eapi
        except profiles.NonexistentProfile:
            return get_eapi('0')

    @klass.jit_attr
    def pkg_masks(self):
        """Package masks from profiles/package.mask."""
        return frozenset(self.base_profile.masks[1])

    @klass.jit_attr
    def pkg_deprecated(self):
        """Deprecated packages from profiles/package.deprecated."""
        return frozenset(self.base_profile.pkg_deprecated[1])


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
            except PermissionError:
                if platform.uname().release < '4.18':
                    raise repo_errors.InitializationError(
                        'fuse mounts in user namespaces require linux >= 4.18')
                raise
        super().__init__(location, *args, **kwargs)

    def _pre_sync(self):
        if os.path.ismount(self.location):
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

        # First try using mount binary to automatically handle setting up loop
        # device -- this only works with real root perms since loopback device
        # mounting (losetup) doesn't work in user namespaces.
        #
        # TODO: switch to capture_output=True when >= py3.7
        ret = subprocess.run(
            ['mount', self._sqfs, self.location],
            stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        )

        if ret.returncode == 0:
            return
        elif ret.returncode not in (1, 32):
            # fail out if not a permissions issue (regular or loopback failure inside userns)
            self._failed_cmd(ret, 'mounting')

        # fallback to using squashfuse
        try:
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
