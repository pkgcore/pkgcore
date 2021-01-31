"""make.conf translator.

Converts portage config files into :obj:`pkgcore.config` form.
"""

__all__ = (
    'PortageConfig', 'SecurityUpgradesViaProfile',
)

import configparser
import errno
import os
from collections import OrderedDict

from snakeoil.bash import read_bash_dict
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.mappings import DictMixin, ImmutableDict
from snakeoil.osutils import access, listdir_files, pjoin

from .. import const
from .. import exceptions as base_errors
from ..config import basics
from ..config import errors as config_errors
from ..config.hint import configurable
from ..fs.livefs import sorted_scan
from ..log import logger
from ..pkgsets.glsa import SecurityUpgrades
from . import const as econst
from . import profiles, repo_objs
from .misc import optimize_incrementals
from .repository import errors as repo_errors


def my_convert_hybrid(manager, val, arg_type):
    """Modified convert_hybrid using a sequence of strings for section_refs."""
    if arg_type.startswith('refs:'):
        subtype = 'ref:' + arg_type.split(':', 1)[1]
        return [basics.LazyNamedSectionRef(manager, subtype, name) for name in val]
    return basics.convert_hybrid(manager, val, arg_type)


@configurable({'ebuild_repo': 'ref:repo', 'vdb': 'ref:repo',
               'profile': 'ref:profile'}, typename='pkgset')
def SecurityUpgradesViaProfile(ebuild_repo, vdb, profile):
    """generate a GLSA vuln. pkgset limited by profile

    Args:
        ebuild_repo (:obj:`pkgcore.ebuild.repository.UnconfiguredTree`): target repo
        vdb (:obj:`pkgcore.repository.prototype.tree`): livefs
        profile (:obj:`pkgcore.ebuild.profiles`): target profile

    Returns:
        pkgset of relevant security upgrades
    """
    arch = profile.arch
    if arch is None:
        raise config_errors.ComplexInstantiationError("arch wasn't set in profiles")
    return SecurityUpgrades(ebuild_repo, vdb, arch)


class ParseConfig(configparser.ConfigParser):
    """Custom ConfigParser class to support returning dict objects."""

    def parse_file(self, f, reset=True):
        """Parse config data from a given file handle.

        By default the underlying config data is reset on each call if it
        exists. This allows multiple files to be easily parsed by a single instance
        without combining all the data in one instance.

        Args:
            f: iterable yielding unicode strings (opened file handle)
            reset (boolean): reset config data if it exists before parsing

        Returns:
            dict: default settings
            dict: regular section settings
        """
        if self._defaults and reset:
            self._defaults = self._dict()
        if self._sections and reset:
            self._sections = self._dict()
        # currently we don't reset section proxies as they should affect
        # this direct data dumping
        self.read_file(f)
        return self._defaults, self._sections


class PortageConfig(DictMixin):
    """Support for portage's config file layout."""

    _supported_repo_types = {}

    def __init__(self, location=None, profile_override=None, **kwargs):
        """
        Args:
            location (optional[str]): path to the portage config directory,
                (defaults to /etc/portage)
            profile_override (optional[str]): profile to use instead of the current system
                profile, i.e. the target of the /etc/portage/make.profile symlink
            configroot (optional[str]): location for various portage config files (defaults to /)
            root (optional[str]): target root filesystem (defaults to /)
            buildpkg (optional[bool]): forcibly disable/enable building binpkgs, otherwise
                FEATURES=buildpkg from make.conf is used

        Returns:
            dict: config settings
        """
        self._config = {}

        if location is None:
            location = '/etc/portage'
            # fallback to stub config and profile on non-Gentoo systems
            if not os.path.exists(location):
                location = pjoin(const.DATA_PATH, 'stubconfig')
                profile_override = pjoin(const.DATA_PATH, 'stubrepo/profiles/default')
        elif location == pjoin(const.DATA_PATH, 'stubconfig'):
            # override profile when using stub config
            profile_override = pjoin(const.DATA_PATH, 'stubrepo/profiles/default')

        self.dir = pjoin(
            os.environ.get('PORTAGE_CONFIGROOT', kwargs.pop('configroot', '/')),
            location.lstrip('/'))

        # this actually differs from portage parsing- we allow
        # make.globals to provide vars used in make.conf, portage keeps
        # them separate (kind of annoying)
        #
        # this isn't preserving incremental behaviour for features/use unfortunately

        make_conf = {}
        try:
            self.load_make_conf(make_conf, pjoin(const.CONFIG_PATH, 'make.globals'))
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            raise config_errors.ParsingError("failed to load make.globals") from e
        self.load_make_conf(
            make_conf, pjoin(self.dir, 'make.conf'), required=False,
            allow_sourcing=True, incrementals=True)

        self.root = os.environ.get("ROOT", kwargs.pop('root', make_conf.get("ROOT", "/")))
        gentoo_mirrors = [
            x.rstrip("/") + "/distfiles" for x in make_conf.pop("GENTOO_MIRRORS", "").split()]

        self.features = frozenset(
            optimize_incrementals(make_conf.get('FEATURES', '').split()))

        self._add_sets()
        self._add_profile(profile_override)

        self['vdb'] = basics.AutoConfigSection({
            'class': 'pkgcore.vdb.ondisk.tree',
            'location': pjoin(self.root, 'var', 'db', 'pkg'),
            'cache_location': '/var/cache/edb/dep/var/db/pkg',
        })

        try:
            repos_conf_defaults, repos_conf = self.load_repos_conf(
                pjoin(self.dir, 'repos.conf'))
        except config_errors.ParsingError as e:
            if not getattr(getattr(e, 'exc', None), 'errno', None) == errno.ENOENT:
                raise
            try:
                # fallback to defaults provided by pkgcore
                repos_conf_defaults, repos_conf = self.load_repos_conf(
                    pjoin(const.CONFIG_PATH, 'repos.conf'))
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise config_errors.ParsingError('failed to find a usable repos.conf') from e

        self['ebuild-repo-common'] = basics.AutoConfigSection({
            'class': 'pkgcore.ebuild.repository.tree',
            'default_mirrors': gentoo_mirrors,
            'inherit-only': True,
        })

        repo_map = {}

        for repo_name, repo_opts in list(repos_conf.items()):
            repo_cls = repo_opts.pop('repo-type')
            try:
                repo = repo_cls(
                    self, repo_name=repo_name, repo_opts=repo_opts,
                    repo_map=repo_map, defaults=repos_conf_defaults)
            except repo_errors.UnsupportedRepo as e:
                logger.warning(
                    f'skipping {repo_name!r} repo: unsupported EAPI {str(e.repo.eapi)!r}')
                del repos_conf[repo_name]
                continue

            self[repo_name] = basics.AutoConfigSection(repo)

        # XXX: Hack for portage-2 profile format support. We need to figure out how
        # to dynamically create this from the config at runtime on attr access.
        profiles.ProfileNode._repo_map = ImmutableDict(repo_map)

        self._make_repo_syncers(repos_conf, make_conf)
        repos = [name for name in repos_conf.keys()]
        if repos:
            self['repo-stack'] = basics.FakeIncrementalDictConfigSection(
                my_convert_hybrid, {
                    'class': 'pkgcore.repository.multiplex.config_tree',
                    'repos': tuple(repos)})

            self['vuln'] = basics.AutoConfigSection({
                'class': SecurityUpgradesViaProfile,
                'ebuild_repo': 'repo-stack',
                'vdb': 'vdb',
                'profile': 'profile',
            })

        # check if package building was forced on by the user
        forced_buildpkg = kwargs.pop('buildpkg', False)
        if forced_buildpkg:
            make_conf['FEATURES'] += ' buildpkg'

        # now add the fetcher- we delay it till here to clean out the environ
        # it passes to the command.
        # *everything* in make_conf must be str values also.
        self._add_fetcher(make_conf)

        # finally... domain.
        make_conf.update({
            'class': 'pkgcore.ebuild.domain.domain',
            'repos': tuple(repos),
            'fetcher': 'fetcher',
            'default': True,
            'vdb': ('vdb',),
            'profile': 'profile',
            'name': 'livefs',
            'root': self.root,
            'config_dir': self.dir,
        })

        self['livefs'] = basics.FakeIncrementalDictConfigSection(
            my_convert_hybrid, make_conf)

    def __setitem__(self, key, value):
        self._config[key] = value

    def __getitem__(self, key):
        return self._config[key]

    def __delitem__(self, key):
        del self._config[key]

    def keys(self):
        return iter(self._config.keys())

    @staticmethod
    def load_make_conf(vars_dict, path, allow_sourcing=False, required=True,
                       allow_recurse=True, incrementals=False):
        """parse make.conf files

        Args:
            vars_dict (dict): dictionary to add parsed variables to
            path (str): path to the make.conf which can be a regular file or
                directory, if a directory is passed all the non-hidden files within
                that directory are parsed in alphabetical order.
        """
        sourcing_command = 'source' if allow_sourcing else None

        if allow_recurse:
            files = sorted_scan(
                os.path.realpath(path), follow_symlinks=True, nonexistent=True,
                hidden=False, backup=False)
        else:
            files = (path,)

        for fp in files:
            try:
                new_vars = read_bash_dict(
                    fp, vars_dict=vars_dict, sourcing_command=sourcing_command)
            except PermissionError as e:
                raise base_errors.PermissionDenied(fp, write=False) from e
            except EnvironmentError as e:
                if e.errno != errno.ENOENT or required:
                    raise config_errors.ParsingError(f"parsing {fp!r}", exception=e) from e
                return

            if incrementals:
                for key in econst.incrementals:
                    if key in vars_dict and key in new_vars:
                        new_vars[key] = f"{vars_dict[key]} {new_vars[key]}"
            # quirk of read_bash_dict; it returns only what was mutated.
            vars_dict.update(new_vars)

    @classmethod
    def load_repos_conf(cls, path):
        """parse repos.conf files

        Args:
            path (str): path to the repos.conf which can be a regular file or
                directory, if a directory is passed all the non-hidden files within
                that directory are parsed in alphabetical order.

        Returns:
            dict: global repo settings
            dict: repo settings
        """
        main_defaults = {}
        repos = {}

        parser = ParseConfig()

        for fp in sorted_scan(
                os.path.realpath(path), follow_symlinks=True, nonexistent=True,
                hidden=False, backup=False):
            try:
                with open(fp) as f:
                    defaults, repo_confs = parser.parse_file(f)
            except PermissionError as e:
                raise base_errors.PermissionDenied(fp, write=False) from e
            except EnvironmentError as e:
                raise config_errors.ParsingError(f"parsing {fp!r}", exception=e) from e
            except configparser.Error as e:
                raise config_errors.ParsingError(f"repos.conf: {fp!r}", exception=e) from e

            if defaults and main_defaults:
                logger.warning(f"repos.conf: parsing {fp!r}: overriding DEFAULT section")
            main_defaults.update(defaults)

            for name, repo_conf in repo_confs.items():
                if name in repos:
                    logger.warning(f"repos.conf: parsing {fp!r}: overriding {name!r} repo")

                # ignore repo if location is unset
                location = repo_conf.get('location', None)
                if location is None:
                    logger.warning(
                        f"repos.conf: parsing {fp!r}: "
                        f"{name!r} repo missing location setting, ignoring repo")
                    continue
                location = os.path.expanduser(location)
                if os.path.isabs(location):
                    repo_conf['location'] = location
                else:
                    # support relative paths based on where repos.conf is located
                    repo_conf['location'] = os.path.abspath(
                        pjoin(os.path.dirname(path), location))

                # repo type defaults to ebuild for compat with portage
                repo_type = repo_conf.get('repo-type', 'ebuild-v1')
                try:
                    repo_conf['repo-type'] = cls._supported_repo_types[repo_type]
                except KeyError:
                    logger.warning(
                        f"repos.conf: parsing {fp!r}: "
                        f"{name!r} repo has unsupported repo-type {repo_type!r}, "
                        "ignoring repo")
                    continue

                # Priority defaults to zero if unset or invalid for ebuild repos
                # while binpkg repos have the lowest priority by default.
                priority = repo_conf.get('priority', None)
                if priority is None:
                    if repo_type.startswith('binpkg'):
                        priority = -10000
                    else:
                        priority = 0

                try:
                    priority = int(priority)
                except ValueError:
                    logger.warning(
                        f"repos.conf: parsing {fp!r}: {name!r} repo has invalid priority "
                        f"setting: {priority!r} (defaulting to 0)")
                    priority = 0
                finally:
                    repo_conf['priority'] = priority

                # register repo
                repos[name] = repo_conf

        if repos:
            # the default repo is gentoo if unset and gentoo exists
            default_repo = main_defaults.get('main-repo', 'gentoo')
            if default_repo not in repos:
                raise config_errors.UserConfigError(
                    f"repos.conf: default repo {default_repo!r} is undefined or invalid")

            if 'main-repo' not in main_defaults:
                main_defaults['main-repo'] = default_repo

            # the default repo has a low priority if unset or zero
            if repos[default_repo]['priority'] == 0:
                repos[default_repo]['priority'] = -1000

        # sort repos via priority, in this case high values map to high priorities
        repos = OrderedDict(
            (k, v) for k, v in
            sorted(repos.items(), key=lambda d: d[1]['priority'], reverse=True))

        return main_defaults, repos

    def _make_repo_syncers(self, repos_conf, make_conf, allow_timestamps=True):
        """generate syncing configs for known repos"""
        rsync_opts = None
        usersync = 'usersync' in self.features

        for repo_name, repo_opts in repos_conf.items():
            d = {'basedir': repo_opts['location'], 'usersync': usersync}

            sync_type = repo_opts.get('sync-type', None)
            sync_uri = repo_opts.get('sync-uri', None)

            if sync_uri:
                # prefix non-native protocols
                if (sync_type is not None and not sync_uri.startswith(sync_type)):
                    sync_uri = f'{sync_type}+{sync_uri}'

                d['uri'] = sync_uri
                d['opts'] = repo_opts.get('sync-opts', '')

                if sync_type == 'rsync':
                    if rsync_opts is None:
                        # various make.conf options used by rsync-based syncers
                        rsync_opts = self._isolate_rsync_opts(make_conf)
                    d.update(rsync_opts)
                    if allow_timestamps:
                        d['class'] = 'pkgcore.sync.rsync.rsync_timestamp_syncer'
                    else:
                        d['class'] = 'pkgcore.sync.rsync.rsync_syncer'
                else:
                    d['class'] = 'pkgcore.sync.base.GenericSyncer'
            elif sync_uri is None:
                # try to autodetect syncing mechanism if sync-uri is missing
                d['class'] = 'pkgcore.sync.base.AutodetectSyncer'
            else:
                # disable syncing if sync-uri is explicitly unset
                d['class'] = 'pkgcore.sync.base.DisabledSyncer'

            name = 'sync:' + repo_name
            self[name] = basics.AutoConfigSection(d)

    def _add_sets(self):
        self["world"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.filelist.WorldFile",
            "location": pjoin(self.root, econst.WORLD_FILE.lstrip('/'))})
        self["system"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.system.SystemSet",
            "profile": "profile"})
        self["installed"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.installed.Installed",
            "vdb": "vdb"})
        self["versioned-installed"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.installed.VersionedInstalled",
            "vdb": "vdb"})

        set_fp = pjoin(self.dir, "sets")
        try:
            for setname in listdir_files(set_fp):
                # Potential for name clashes here, those will just make
                # the set not show up in config.
                if setname in ("system", "world"):
                    logger.warning(
                        "user defined set %r is disallowed; ignoring",
                        pjoin(set_fp, setname))
                    continue
                self[setname] = basics.AutoConfigSection({
                    "class": "pkgcore.pkgsets.filelist.FileList",
                    "location": pjoin(set_fp, setname)})
        except FileNotFoundError:
            pass

    def _find_profile_path(self, profile_override):
        if profile_override is None:
            make_profile = pjoin(self.dir, 'make.profile')
            if not os.path.islink(make_profile):
                raise config_errors.UserConfigError(f'invalid symlink: {make_profile!r}')
            path = os.path.realpath(make_profile)
        else:
            path = os.path.realpath(profile_override)

        if not os.path.exists(path):
            if profile_override is None:
                raise config_errors.UserConfigError(f'broken symlink: {make_profile!r}')
            else:
                raise config_errors.UserConfigError(f'nonexistent profile: {profile_override!r}')
        return path

    def _add_profile(self, profile_override=None):
        profile = self._find_profile_path(profile_override)
        paths = profiles.OnDiskProfile.split_abspath(profile)
        if paths is None:
            raise config_errors.UserConfigError(
                '%r expands to %r, but no profile detected' %
                (pjoin(self.dir, 'make.profile'), profile))

        user_profile_path = pjoin(self.dir, 'profile')
        if os.path.isdir(user_profile_path):
            self["profile"] = basics.AutoConfigSection({
                "class": "pkgcore.ebuild.profiles.UserProfile",
                "parent_path": paths[0],
                "parent_profile": paths[1],
                "user_path": user_profile_path,
            })
        else:
            self["profile"] = basics.AutoConfigSection({
                "class": "pkgcore.ebuild.profiles.OnDiskProfile",
                "basepath": paths[0],
                "profile": paths[1],
            })

    def _add_fetcher(self, make_conf):
        fetchcommand = make_conf.pop("FETCHCOMMAND")
        resumecommand = make_conf.pop("RESUMECOMMAND", fetchcommand)

        fetcher_dict = {
            "class": "pkgcore.fetch.custom.fetcher",
            "distdir": os.path.normpath(os.environ.get("DISTDIR", make_conf.pop("DISTDIR"))),
            "command": fetchcommand,
            "resume_command": resumecommand,
            "attempts": make_conf.pop("FETCH_ATTEMPTS", '10'),
        }
        self["fetcher"] = basics.AutoConfigSection(fetcher_dict)

    def _isolate_rsync_opts(self, options):
        """
        pop the misc RSYNC related options littered in make.conf, returning
        a base rsync dict
        """
        base = {}
        opts = []
        extra_opts = []

        opts.extend(options.pop('PORTAGE_RSYNC_OPTS', '').split())
        extra_opts.extend(options.pop('PORTAGE_RSYNC_EXTRA_OPTS', '').split())

        timeout = options.pop('PORTAGE_RSYNC_INITIAL_TIMEOUT', None)
        if timeout is not None:
            base['connection_timeout'] = timeout

        retries = options.pop('PORTAGE_RSYNC_RETRIES', None)
        if retries is not None:
            try:
                retries = int(retries)
                if retries < 0:
                    retries = 10000
                base['retries'] = str(retries)
            except ValueError:
                pass

        proxy = options.pop('RSYNC_PROXY', None)
        if proxy is not None:
            base['proxy'] = proxy.strip()

        if opts:
            base['opts'] = tuple(opts)
        if extra_opts:
            base['extra_opts'] = tuple(extra_opts)

        return base

    def _make_cache(self, cache_format, repo_path):
        """Configure repo cache."""
        # Use md5 cache if it exists or the option is selected, otherwise default
        # to the old flat hash format in /var/cache/edb/dep/*.
        if (os.path.exists(pjoin(repo_path, 'metadata', 'md5-cache')) or
                cache_format == 'md5-dict'):
            kls = 'pkgcore.cache.flat_hash.md5_cache'
            cache_parent_dir = pjoin(repo_path, 'metadata', 'md5-cache')
        else:
            kls = 'pkgcore.cache.flat_hash.database'
            repo_path = pjoin('/var/cache/edb/dep', repo_path.lstrip('/'))
            cache_parent_dir = repo_path

        while not os.path.exists(cache_parent_dir):
            cache_parent_dir = os.path.dirname(cache_parent_dir)
        readonly = (not access(cache_parent_dir, os.W_OK | os.X_OK))

        return basics.AutoConfigSection({
            'class': kls,
            'location': repo_path,
            'readonly': readonly
        })

    def _register_repo_type(supported_repo_types):
        """Decorator to register supported repo types."""
        def _wrap_func(func):
            def wrapped(*args, **kwargs):
                return func(*args, **kwargs)
            name = func.__name__[6:].replace('_', '-')
            supported_repo_types[name] = func
            return wrapped
        return _wrap_func

    @_register_repo_type(_supported_repo_types)
    def _repo_ebuild_v1(self, repo_name, repo_opts, repo_map,
                        defaults, repo_obj=None, repo_dict=None):
        """Create ebuild repo v1 configuration."""
        repo_path = repo_opts['location']

        # XXX: Hack for portage-2 profile format support.
        if repo_obj is None:
            repo_obj = repo_objs.RepoConfig(repo_path, repo_name)
        repo_map[repo_obj.repo_id] = repo_path

        # repo configs
        repo_conf = {
            'class': 'pkgcore.ebuild.repo_objs.RepoConfig',
            'config_name': repo_name,
            'location': repo_path,
            'syncer': 'sync:' + repo_name,
        }
        if repo_dict is not None:
            repo_conf.update(repo_dict)

        # repo trees
        repo = {
            'inherit': ('ebuild-repo-common',),
            'repo_config': 'conf:' + repo_name,
        }

        # metadata cache
        if repo_obj.cache_format is not None:
            cache_name = 'cache:' + repo_name
            self[cache_name] = self._make_cache(repo_obj.cache_format, repo_path)
            repo['cache'] = cache_name

        if repo_name == defaults['main-repo']:
            repo_conf['default'] = True
            repo['default'] = True

        self['conf:' + repo_name] = basics.AutoConfigSection(repo_conf)
        return repo

    @_register_repo_type(_supported_repo_types)
    def _repo_sqfs_v1(self, *args, **kwargs):
        """Create ebuild squashfs repo v1 configuration."""
        repo_name = kwargs['repo_name']
        repo_opts = kwargs['repo_opts']

        repo_path = repo_opts['location']
        sqfs_file = os.path.basename(repo_opts['sync-uri'])
        # XXX: Hack for portage-2 profile format support.
        kwargs['repo_obj'] = repo_objs.SquashfsRepoConfig(sqfs_file, repo_path, repo_name)

        repo_dict = {
            'class': 'pkgcore.ebuild.repo_objs.SquashfsRepoConfig',
            'sqfs_file': sqfs_file,
        }
        kwargs['repo_dict'] = repo_dict
        return self._repo_ebuild_v1(*args, **kwargs)

    @_register_repo_type(_supported_repo_types)
    def _repo_binpkg_v1(self, repo_name, repo_opts, **kwargs):
        """Create binpkg repo v1 configuration."""
        repo = {
            'class': 'pkgcore.binpkg.repository.tree',
            'repo_id': repo_name,
            'location': repo_opts['location'],
        }
        return repo
