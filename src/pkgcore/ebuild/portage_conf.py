# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""make.conf translator.

Converts portage config files into :obj:`pkgcore.config` form.
"""

__all__ = (
    "SecurityUpgradesViaProfile", "make_repo_syncers",
    "add_sets", "add_profile", "add_fetcher", "make_cache",
    "load_make_conf", "load_repos_conf", "config_from_make_conf",
)

import configparser
from collections import OrderedDict
import os

from snakeoil.bash import read_bash_dict
from snakeoil.currying import wrap_exception
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.demandload import demandload
from snakeoil.mappings import ImmutableDict
from snakeoil.osutils import access, normpath, abspath, listdir_files, pjoin, ensure_dirs

from pkgcore import const
from pkgcore.config import basics, configurable
from pkgcore.ebuild import const as econst, profiles
from pkgcore.ebuild.repo_objs import RepoConfig
from pkgcore.fs.livefs import sorted_scan
from pkgcore.pkgsets.glsa import SecurityUpgrades

demandload(
    'errno',
    'pkgcore.config:errors',
    'pkgcore.log:logger',
)


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
        raise errors.ComplexInstantiationError("arch wasn't set in profiles")
    return SecurityUpgrades(ebuild_repo, vdb, arch)


def isolate_rsync_opts(options):
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


def make_repo_syncers(config, repos_conf, make_conf, allow_timestamps=True):
    """generate syncing configs for known repos"""
    rsync_opts = None

    for repo_name, repo_opts in repos_conf.items():
        d = {'basedir': repo_opts['location']}

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
                    rsync_opts = isolate_rsync_opts(make_conf)
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
        config[name] = basics.AutoConfigSection(d)


def add_sets(config, root, config_dir):
    config["world"] = basics.AutoConfigSection({
        "class": "pkgcore.pkgsets.filelist.WorldFile",
        "location": pjoin(root, econst.WORLD_FILE.lstrip('/'))})
    config["system"] = basics.AutoConfigSection({
        "class": "pkgcore.pkgsets.system.SystemSet",
        "profile": "profile"})
    config["installed"] = basics.AutoConfigSection({
        "class": "pkgcore.pkgsets.installed.Installed",
        "vdb": "vdb"})
    config["versioned-installed"] = basics.AutoConfigSection({
        "class": "pkgcore.pkgsets.installed.VersionedInstalled",
        "vdb": "vdb"})

    set_fp = pjoin(config_dir, "sets")
    try:
        for setname in listdir_files(set_fp):
            # Potential for name clashes here, those will just make
            # the set not show up in config.
            if setname in ("system", "world"):
                logger.warning(
                    "user defined set %r is disallowed; ignoring",
                    pjoin(set_fp, setname))
                continue
            config[setname] = basics.AutoConfigSection({
                "class": "pkgcore.pkgsets.filelist.FileList",
                "location": pjoin(set_fp, setname)})
    except FileNotFoundError:
        pass


def _find_profile_link(config_dir):
    make_profile = pjoin(config_dir, 'make.profile')
    try:
        return normpath(abspath(
            pjoin(config_dir, os.readlink(make_profile))))
    except EnvironmentError as e:
        if oe.errno in (errno.ENOENT, errno.EINVAL):
            raise errors.ComplexInstantiationError(
                f"{make_profile} must be a symlink pointing to a real target") from e
        raise errors.ComplexInstantiationError(
            f"{make_profile}: unexpected error- {e.strerror}") from e

def add_profile(config, config_dir, profile_override=None):
    if profile_override is None:
        profile = _find_profile_link(config_dir)
    else:
        profile = normpath(abspath(profile_override))
        if not os.path.exists(profile):
            raise errors.ComplexInstantiationError(f"{profile} doesn't exist")

    paths = profiles.OnDiskProfile.split_abspath(profile)
    if paths is None:
        raise errors.ComplexInstantiationError(
            '%s expands to %s, but no profile detected' %
            (pjoin(config_dir, 'make.profile'), profile))

    user_profile_path = pjoin(config_dir, 'profile')
    if os.path.isdir(user_profile_path):
        config["profile"] = basics.AutoConfigSection({
            "class": "pkgcore.ebuild.profiles.UserProfile",
            "parent_path": paths[0],
            "parent_profile": paths[1],
            "user_path": user_profile_path,
        })
    else:
        config["profile"] = basics.AutoConfigSection({
            "class": "pkgcore.ebuild.profiles.OnDiskProfile",
            "basepath": paths[0],
            "profile": paths[1],
        })


def add_fetcher(config, make_conf):
    fetchcommand = make_conf.pop("FETCHCOMMAND")
    resumecommand = make_conf.pop("RESUMECOMMAND", fetchcommand)

    fetcher_dict = {
        "class": "pkgcore.fetch.custom.fetcher",
        "distdir": normpath(os.environ.get("DISTDIR", make_conf.pop("DISTDIR"))),
        "command": fetchcommand,
        "resume_command": resumecommand,
        "attempts": make_conf.pop("FETCH_ATTEMPTS", '10'),
    }
    config["fetcher"] = basics.AutoConfigSection(fetcher_dict)


def make_cache(cache_format, repo_path):
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


def load_make_conf(vars_dict, path, allow_sourcing=False, required=True,
                   allow_recurse=True, incrementals=False):
    """parse make.conf files

    Args:
        vars_dict (dict): dictionary to add parsed variables to
        path (str): path to the make.conf which can be a regular file or
            directory, if a directory is passed all the non-hidden files within
            that directory are parsed in alphabetical order.
    """
    sourcing_command = None
    if allow_sourcing:
        sourcing_command = 'source'

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
            raise errors.PermissionDeniedError(fp, write=False) from e
        except EnvironmentError as e:
            if e.errno != errno.ENOENT or required:
                raise errors.ParsingError("parsing %r" % (fp,), exception=e) from e
            return

        if incrementals:
            for key in econst.incrementals:
                if key in vars_dict and key in new_vars:
                    new_vars[key] = f"{vars_dict[key]} {new_vars[key]}"
        # quirk of read_bash_dict; it returns only what was mutated.
        vars_dict.update(new_vars)


def load_repos_conf(path):
    """parse repos.conf files

    Args:
        path (str): path to the repos.conf which can be a regular file or
            directory, if a directory is passed all the non-hidden files within
            that directory are parsed in alphabetical order.

    Returns:
        dict: global repo settings
        dict: repo settings
    """
    defaults = {}
    repos = {}

    for fp in sorted_scan(
            os.path.realpath(path), follow_symlinks=True, nonexistent=True,
            hidden=False, backup=False):
        config = configparser.ConfigParser()
        try:
            with open(fp) as f:
                config.read_file(f)
        except PermissionError as e:
            raise errors.PermissionDeniedError(fp, write=False) from e
        except EnvironmentError as e:
            raise errors.ParsingError(f"parsing {fp!r}", exception=e) from e
        except configparser.Error as e:
            raise errors.ParsingError(f"repos.conf: {fp!r}", exception=e) from e

        defaults_data = config.defaults()
        if defaults_data and defaults:
            logger.warning(f"repos.conf: parsing {fp!r}: overriding DEFAULT section")
        defaults.update(defaults_data)

        for name in config.sections():
            if name in repos:
                logger.warning(f"repos.conf: parsing {fp!r}: overriding {name!r} repo")
            repo_data = dict(config.items(name))

            # ignore repo if location is unset
            location = repo_data.get('location', None)
            if location is None:
                logger.warning(
                    f"repos.conf: parsing {fp!r}: "
                    f"{name!r} repo missing location setting, ignoring repo")
                continue
            repo_data['location'] = os.path.abspath(location)

            # repo priority defaults to zero if unset or invalid
            priority = repo_data.get('priority', 0)
            try:
                priority = int(priority)
            except ValueError:
                logger.warning(
                    f"repos.conf: parsing {fp!r}: {name!r} repo has invalid priority "
                    f"setting: {priority!r} (defaulting to 0)")
                priority = 0
            finally:
                repo_data['priority'] = priority

            # register repo
            repos[name] = repo_data

    if repos:
        # the default repo is gentoo if unset and gentoo exists
        default_repo = defaults.get('main-repo', 'gentoo')
        if default_repo not in repos:
            raise errors.ConfigurationError(
                f"default repo {default_repo!r} is undefined or invalid")

        if 'main-repo' not in defaults:
            defaults['main-repo'] = default_repo

        # the default repo has a low priority if unset or zero
        if repos[default_repo]['priority'] == 0:
            repos[default_repo]['priority'] = -1000

    # sort repos via priority, in this case high values map to high priorities
    repos = OrderedDict(
        (k, v) for k, v in
        sorted(repos.items(), key=lambda d: d[1]['priority'], reverse=True))

    del config
    return defaults, repos


@configurable({'config_dir': 'str'}, typename='configsection')
@wrap_exception(errors.ParsingError, "while loading portage config", pass_error='exception')
def config_from_make_conf(location=None, profile_override=None, **kwargs):
    """generate a config using portage's config files

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

    # this actually differs from portage parsing- we allow
    # make.globals to provide vars used in make.conf, portage keeps
    # them separate (kind of annoying)

    config_dir = location if location is not None else '/etc/portage'
    config_dir = pjoin(
        os.environ.get('PORTAGE_CONFIGROOT', kwargs.pop('configroot', '/')),
        config_dir.lstrip('/'))

    # this isn't preserving incremental behaviour for features/use unfortunately

    make_conf = {}
    try:
        load_make_conf(make_conf, pjoin(const.CONFIG_PATH, 'make.globals'))
    except IGNORED_EXCEPTIONS:
        raise
    except Exception as e:
        raise errors.ParsingError("failed to load make.globals") from e
    load_make_conf(
        make_conf, pjoin(config_dir, 'make.conf'), required=False,
        allow_sourcing=True, incrementals=True)

    root = os.environ.get("ROOT", kwargs.pop('root', make_conf.get("ROOT", "/")))
    gentoo_mirrors = [
        x.rstrip("/") + "/distfiles" for x in make_conf.pop("GENTOO_MIRRORS", "").split()]

    # this is flawed... it'll pick up -some-feature
    features = make_conf.get("FEATURES", "").split()

    config = {}

    # sets...
    add_sets(config, root, config_dir)

    add_profile(config, config_dir, profile_override)

    kwds = {
        "class": "pkgcore.vdb.ondisk.tree",
        "location": pjoin(root, 'var', 'db', 'pkg'),
        "cache_location": '/var/cache/edb/dep/var/db/pkg',
    }
    config["vdb"] = basics.AutoConfigSection(kwds)

    try:
        repos_conf_defaults, repos_conf = load_repos_conf(pjoin(config_dir, 'repos.conf'))
    except errors.ParsingError as e:
        if not getattr(getattr(e, 'exc', None), 'errno', None) == errno.ENOENT:
            raise
        try:
            # fallback to defaults provided by pkgcore
            repos_conf_defaults, repos_conf = load_repos_conf(
                pjoin(const.CONFIG_PATH, 'repos.conf'))
        except IGNORED_EXCEPTIONS:
            raise
        except Exception as e:
            raise errors.ParsingError("failed to find a usable repos.conf") from e

    make_repo_syncers(config, repos_conf, make_conf)

    config['ebuild-repo-common'] = basics.AutoConfigSection({
        'class': 'pkgcore.ebuild.repository.tree',
        'default_mirrors': gentoo_mirrors,
        'inherit-only': True,
        'ignore_paludis_versioning': ('ignore-paludis-versioning' in features),
    })

    repo_map = {}

    for repo_name, repo_opts in repos_conf.items():
        repo_path = repo_opts['location']

        # XXX: Hack for portage-2 profile format support.
        repo_config = RepoConfig(repo_path, repo_name)
        repo_map[repo_config.repo_id] = repo_path

        # repo configs
        repo_conf = {
            'class': 'pkgcore.ebuild.repo_objs.RepoConfig',
            'config_name': repo_name,
            'location': repo_path,
            'syncer': 'sync:' + repo_name,
        }

        # repo trees
        repo = {
            'inherit': ('ebuild-repo-common',),
            'repo_config': 'conf:' + repo_name,
        }

        # metadata cache
        if repo_config.cache_format is not None:
            cache_name = 'cache:' + repo_name
            config[cache_name] = make_cache(repo_config.cache_format, repo_path)
            repo['cache'] = cache_name

        if repo_name == repos_conf_defaults['main-repo']:
            repo_conf['default'] = True
            repo['default'] = True

        config['conf:' + repo_name] = basics.AutoConfigSection(repo_conf)
        config[repo_name] = basics.AutoConfigSection(repo)

    # XXX: Hack for portage-2 profile format support. We need to figure out how
    # to dynamically create this from the config at runtime on attr access.
    profiles.ProfileNode._repo_map = ImmutableDict(repo_map)

    repos = [name for name in repos_conf.keys()]
    if repos:
        if len(repos) > 1:
            config['repo-stack'] = basics.FakeIncrementalDictConfigSection(
                my_convert_hybrid, {
                    'class': 'pkgcore.repository.multiplex.config_tree',
                    'repos': tuple(repos)})
        else:
            config['repo-stack'] = basics.section_alias(repos[0], 'repo')

        config['vuln'] = basics.AutoConfigSection({
            'class': SecurityUpgradesViaProfile,
            'ebuild_repo': 'repo-stack',
            'vdb': 'vdb',
            'profile': 'profile',
        })
        config['glsa'] = basics.section_alias(
            'vuln', SecurityUpgradesViaProfile.pkgcore_config_type.typename)

    # binpkg.
    forced_buildpkg = kwargs.pop('buildpkg', False)
    buildpkg = 'buildpkg' in features or forced_buildpkg
    pkgdir = os.environ.get("PKGDIR", make_conf.get('PKGDIR', None))
    if pkgdir is not None:
        try:
            pkgdir = abspath(pkgdir)
        except FileNotFoundError:
            if buildpkg or set(features).intersection(
                    ('pristine-buildpkg', 'buildsyspkg', 'unmerge-backup')):
                logger.warning("disabling buildpkg related features since PKGDIR doesn't exist")
            pkgdir = None
        else:
            if not ensure_dirs(pkgdir, mode=0o755, minimal=True):
                logger.warning("disabling buildpkg related features since PKGDIR either doesn't "
                               "exist, or lacks 0755 minimal permissions")
                pkgdir = None
    else:
        if buildpkg or set(features).intersection(
                ('pristine-buildpkg', 'buildsyspkg', 'unmerge-backup')):
            logger.warning("disabling buildpkg related features since PKGDIR is unset")

    # yes, round two; may be disabled from above and massive else block sucks
    if pkgdir is not None:
        if pkgdir and os.path.isdir(pkgdir):
            config['binpkg'] = basics.ConfigSectionFromStringDict({
                'class': 'pkgcore.binpkg.repository.tree',
                'repo_id': 'binpkg',
                'location': pkgdir,
                'ignore_paludis_versioning': str('ignore-paludis-versioning' in features),
            })
            repos.append('binpkg')
            # inject feature to enable trigger
            if forced_buildpkg:
                make_conf['FEATURES'] += ' buildpkg'
    elif 'buildpkg' in features:
        # disable feature due to pkgdir issues so trigger isn't added
        make_conf['FEATURES'] += ' -buildpkg'

    # now add the fetcher- we delay it till here to clean out the environ
    # it passes to the command.
    # *everything* in make_conf must be str values also.
    add_fetcher(config, make_conf)

    # finally... domain.
    make_conf.update({
        'class': 'pkgcore.ebuild.domain.domain',
        'repos': tuple(repos),
        'fetcher': 'fetcher',
        'default': True,
        'vdb': ('vdb',),
        'profile': 'profile',
        'name': 'livefs',
        'root': root,
        'config_dir': config_dir,
    })

    config['livefs'] = basics.FakeIncrementalDictConfigSection(
        my_convert_hybrid, make_conf)

    return config
