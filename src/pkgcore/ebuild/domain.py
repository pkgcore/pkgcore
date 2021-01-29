"""
gentoo configuration domain
"""

__all__ = ("domain",)

# XXX doc this up better...

import copy
import os
import re
import tempfile
from collections import defaultdict
from functools import partial
from itertools import chain
from multiprocessing import cpu_count
from operator import itemgetter

from snakeoil import klass
from snakeoil.bash import iter_read_bash, read_bash_dict
from snakeoil.cli.exceptions import find_user_exception
from snakeoil.data_source import local_source
from snakeoil.log import suppress_logging
from snakeoil.mappings import ImmutableDict, ProtectedDict
from snakeoil.osutils import pjoin
from snakeoil.process.spawn import spawn_get_output
from snakeoil.sequences import predicate_split, split_negations, stable_unique

from ..binpkg import repository as binary_repo
from ..cache.flat_hash import md5_cache
from ..config import errors as config_errors
from ..config.domain import Failure
from ..config.domain import domain as config_domain
from ..config.hint import ConfigHint
from ..fs.livefs import iter_scan, sorted_scan
from ..log import logger
from ..repository import errors as repo_errors
from ..repository import filtered
from ..repository.util import RepositoryGroup
from ..restrictions import packages, values
from ..restrictions.delegated import delegate
from ..util.parserestrict import ParseError, parse_match
from . import const
from . import repository as ebuild_repo
from .atom import atom as _atom
from .misc import (ChunkedDataDict, chunked_data, collapsed_restrict_to_data,
                   incremental_expansion, incremental_expansion_license,
                   non_incremental_collapsed_restrict_to_data,
                   optimize_incrementals)
from .portage_conf import PortageConfig
from .repo_objs import OverlayedLicenses, RepoConfig
from .triggers import GenerateTriggers


def package_masks(iterable):
    for line, lineno, path in iterable:
        try:
            yield parse_match(line), line, lineno, path
        except ParseError as e:
            logger.warning(f'{path!r}, line {lineno}: parsing error: {e}')


def package_keywords_splitter(iterable):
    for line, lineno, path in iterable:
        v = line.split()
        try:
            yield parse_match(v[0]), tuple(v[1:]), line, lineno, path
        except ParseError as e:
            logger.warning(f'{path!r}, line {lineno}: parsing error: {e}')


def package_env_splitter(basedir, iterable):
    for line, lineno, path in iterable:
        val = line.split()
        if len(val) == 1:
            logger.warning(f"{path!r}, line {lineno}: missing file reference: {line!r}")
            continue
        paths = []
        for env_file in val[1:]:
            fp = pjoin(basedir, env_file)
            if os.path.exists(fp):
                paths.append(fp)
            else:
                logger.warning(f"{path!r}, line {lineno}: nonexistent file: {fp!r}")
        try:
            yield parse_match(val[0]), tuple(paths), line, lineno, path
        except ParseError as e:
            logger.warning(f'{path!r}, line {lineno}: parsing error: {e}')


def apply_mask_filter(globs, atoms, pkg, mode):
    # mode is ignored; non applicable.
    for r in chain(globs, atoms.get(pkg.key, ())):
        if r.match(pkg):
            return True
    return False


def make_mask_filter(masks, negate=False):
    atoms = defaultdict(list)
    globs = []
    for m in masks:
        if isinstance(m, _atom):
            atoms[m.key].append(m)
        else:
            globs.append(m)
    return delegate(partial(apply_mask_filter, globs, atoms), negate=negate)


def generate_filter(masks, unmasks, *extra):
    # note that we ignore unmasking if masking isn't specified.
    # no point, mainly
    masking = make_mask_filter(masks, negate=True)
    unmasking = make_mask_filter(unmasks, negate=False)
    r = ()
    if masking:
        if unmasking:
            r = (packages.OrRestriction(masking, unmasking, disable_inst_caching=True),)
        else:
            r = (masking,)
    return packages.AndRestriction(disable_inst_caching=True, finalize=True, *(r + extra))


def _read_config_file(path):
    """Read all the data files under a given path."""
    try:
        for fs_obj in iter_scan(path, follow_symlinks=True):
            if not fs_obj.is_reg or '/.' in fs_obj.location:
                continue
            for lineno, line in iter_read_bash(
                    fs_obj.location, allow_line_cont=True, enum_line=True):
                yield line, lineno, fs_obj.location
    except FileNotFoundError:
        pass
    except EnvironmentError as e:
        raise Failure(f"failed reading {path!r}: {e}") from e


def load_property(filename, *, read_func=_read_config_file,
                  parse_func=lambda x: x, fallback=()):
    """Decorator for parsing files using specified read/parse methods.

    :param filename: The filename to parse within the config directory.
    :keyword read_func: An invokable used to read the specified file.
    :keyword parse_func: An invokable used to parse the data.
    :keyword fallback: What to return if the file does not exist.
    :return: A :py:`klass.jit.attr_named` property instance.
    """
    def f(func):
        def _load_and_invoke(func, fallback, self, *args, **kwargs):
            if filename.startswith(os.path.sep):
                # translate root fs calls to prefixed root fs
                path = pjoin(self.root, filename.lstrip(os.path.sep))
            else:
                # assume relative files are inside the config dir
                path = pjoin(self.config_dir, filename)
            if os.path.exists(path):
                data = parse_func(read_func(path))
            else:
                data = fallback
            return func(self, data, *args, **kwargs)
        doc = getattr(func, '__doc__', None)
        jit_attr_named = klass.jit_attr_named(f'_jit_{func.__name__}', doc=doc)
        return jit_attr_named(partial(_load_and_invoke, func, fallback))
    return f


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
#
# note also, that this is rather ebuild centric. it shouldn't be, and
# should be redesigned to be a seperation of configuration
# instantiation manglers, and then the ebuild specific chunk (which is
# selected by config)
class domain(config_domain):

    # XXX ouch, verify this crap and add defaults and stuff
    _types = {
        'profile': 'ref:profile', 'fetcher': 'ref:fetcher',
        'repos': 'lazy_refs:repo', 'vdb': 'lazy_refs:repo', 'name': 'str',
    }
    for _thing in ('root', 'config_dir', 'CHOST', 'CBUILD', 'CTARGET', 'CFLAGS', 'PATH',
                   'PORTAGE_TMPDIR', 'DISTCC_PATH', 'DISTCC_DIR', 'CCACHE_DIR'):
        _types[_thing] = 'str'

    # TODO this is missing defaults
    pkgcore_config_type = ConfigHint(
        _types, typename='domain',
        required=['repos', 'profile', 'vdb', 'fetcher', 'name'],
        allow_unknowns=True)

    del _types, _thing

    def __init__(self, profile, repos, vdb, name=None,
                 root='/', config_dir='/etc/portage', prefix='/', *,
                 fetcher, **settings):
        self.name = name
        self.root = settings["ROOT"] = root
        self.config_dir = config_dir
        self.prefix = prefix
        self.ebuild_hook_dir = pjoin(self.config_dir, 'env')
        self.profile = profile
        self.fetcher = fetcher
        self.__repos = repos
        self.__vdb = vdb

        # prevent critical variables from being changed in make.conf
        for k in self.profile.profile_only_variables.intersection(settings.keys()):
            del settings[k]

        # Protect original settings from being overridden so matching
        # package.env settings can be overlaid properly.
        self._settings = ProtectedDict(settings)

    @load_property("/etc/profile.env", read_func=read_bash_dict)
    def system_profile(self, data):
        # prepend system profile $PATH if it exists
        if 'PATH' in data:
            path = stable_unique(
                data['PATH'].split(os.pathsep) + os.environ['PATH'].split(os.pathsep))
            os.environ['PATH'] = os.pathsep.join(path)
        return ImmutableDict(data)

    @klass.jit_attr_named('_jit_reset_settings', uncached_val=None)
    def settings(self):
        settings = self._settings
        if 'CHOST' in settings and 'CBUILD' not in settings:
            settings['CBUILD'] = settings['CHOST']

        # if unset, MAKEOPTS defaults to CPU thread count
        if 'MAKEOPTS' not in settings:
            settings['MAKEOPTS'] = '-j%i' % cpu_count()

        # reformat env.d and make.conf incrementals
        system_profile_settings = {}
        for x in const.incrementals:
            system_profile_val = self.system_profile.get(x, ())
            make_conf_val = settings.get(x, ())
            if isinstance(system_profile_val, str):
                system_profile_val = tuple(system_profile_val.split())
            if isinstance(make_conf_val, str):
                make_conf_val = tuple(make_conf_val.split())
            system_profile_settings[x] = system_profile_val
            settings[x] = make_conf_val

        # roughly... all incremental stacks should be interpreted left -> right
        # as such we start with the env.d settings, append profile settings,
        # and finally append make.conf settings onto that.
        for k, v in self.profile.default_env.items():
            if k not in settings:
                settings[k] = v
                continue
            if k in const.incrementals:
                settings[k] = system_profile_settings[k] + v + settings[k]

        # next we finalize incrementals.
        for incremental in const.incrementals:
            # Skip USE/ACCEPT_LICENSE for the time being; hack; we need the
            # negations currently so that pkg iuse induced enablings can be
            # disabled by negations. For example, think of the profile doing
            # USE=-cdr for brasero w/ IUSE=+cdr. Similarly, ACCEPT_LICENSE is
            # skipped because negations are required for license filtering.
            if incremental not in settings or incremental in ("USE", "ACCEPT_LICENSE"):
                continue
            settings[incremental] = tuple(incremental_expansion(
                settings[incremental],
                msg_prefix=f'while expanding {incremental}'))

        if 'ACCEPT_KEYWORDS' not in settings:
            raise Failure("No ACCEPT_KEYWORDS setting detected from profile, "
                          "or user config")
        settings['ACCEPT_KEYWORDS'] = incremental_expansion(
            settings['ACCEPT_KEYWORDS'],
            msg_prefix='while expanding ACCEPT_KEYWORDS')

        # pull trigger options from the env
        self._triggers = GenerateTriggers(self, settings)

        return ImmutableDict(settings)

    @property
    def arch(self):
        if "ARCH" not in self.settings:
            raise Failure("No ARCH setting detected from profile, or user config")
        return self.settings['ARCH']

    @property
    def stable_arch(self):
        return self.arch

    @property
    def unstable_arch(self):
        return f"~{self.arch}"

    @klass.jit_attr_named('_jit_reset_features', uncached_val=None)
    def features(self):
        conf_features = list(self.settings.get('FEATURES', ()))
        env_features = os.environ.get('FEATURES', '').split()
        return frozenset(optimize_incrementals(conf_features + env_features))

    @klass.jit_attr_named('_jit_reset_use', uncached_val=None)
    def use(self):
        # append expanded use, FEATURES, and environment defined USE flags
        use = list(self.settings.get('USE', ())) + list(self.profile.expand_use(self.settings))

        # hackish implementation; if test is on, flip on the flag
        if "test" in self.features:
            use.append("test")
        if "prefix" in self.features:
            use.append("prefix")

        return frozenset(optimize_incrementals(use + os.environ.get('USE', '').split()))

    @klass.jit_attr_named('_jit_reset_enabled_use', uncached_val=None)
    def enabled_use(self):
        use = ChunkedDataDict()
        use.add_bare_global(*split_negations(self.use))
        use.merge(self.profile.pkg_use)
        use.update_from_stream(chunked_data(k, *v) for k, v in self.pkg_use)
        use.freeze()
        return use

    @klass.jit_attr_none
    def forced_use(self):
        use = ChunkedDataDict()
        use.merge(getattr(self.profile, 'forced_use'))
        use.add_bare_global((), (self.arch,))
        use.freeze()
        return use

    @klass.jit_attr_none
    def stable_forced_use(self):
        use = ChunkedDataDict()
        use.merge(getattr(self.profile, 'stable_forced_use'))
        use.add_bare_global((), (self.arch,))
        use.freeze()
        return use

    @load_property("package.mask", parse_func=package_masks)
    def pkg_masks(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple(x[0] for x in data)

    @load_property("package.unmask", parse_func=package_masks)
    def pkg_unmasks(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple(x[0] for x in data)

    # TODO: deprecated, remove in 0.11
    @load_property("package.keywords", parse_func=package_keywords_splitter)
    def pkg_keywords(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple((x[0], stable_unique(x[1])) for x in data)

    @load_property("package.accept_keywords", parse_func=package_keywords_splitter)
    def pkg_accept_keywords(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple((x[0], stable_unique(x[1])) for x in data)

    @load_property("package.license", parse_func=package_keywords_splitter)
    def pkg_licenses(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple((x[0], stable_unique(x[1])) for x in data)

    @load_property("package.use", parse_func=package_keywords_splitter)
    def pkg_use(self, data, debug=False):
        if debug:
            return tuple(data)
        return tuple((x[0], split_negations(stable_unique(x[1]))) for x in data)

    @load_property("package.env")
    def pkg_env(self, data, debug=False):
        func = partial(package_env_splitter, self.ebuild_hook_dir)
        data = func(data)
        if debug:
            return tuple(data)
        return tuple((x[0], x[1]) for x in data)

    @klass.jit_attr
    def bashrcs(self):
        files = sorted_scan(pjoin(self.config_dir, 'bashrc'), follow_symlinks=True)
        return tuple(local_source(x) for x in files)

    def _pkg_filters(self, pkg_accept_keywords=None, pkg_keywords=None):
        if pkg_accept_keywords is None:
            pkg_accept_keywords = self.pkg_accept_keywords
        if pkg_keywords is None:
            pkg_keywords = self.pkg_keywords

        # ~amd64 -> [amd64, ~amd64]
        default_keywords = set([self.arch])
        default_keywords.update(self.settings['ACCEPT_KEYWORDS'])
        for x in self.settings['ACCEPT_KEYWORDS']:
            if x.startswith("~"):
                default_keywords.add(x.lstrip("~"))

        # create keyword filters
        accept_keywords = (
            pkg_keywords + pkg_accept_keywords + self.profile.accept_keywords)
        filters = [self._make_keywords_filter(
            default_keywords, accept_keywords,
            incremental="package.keywords" in const.incrementals)]

        # add license filters
        master_license = []
        master_license.extend(self.settings.get('ACCEPT_LICENSE', ()))
        if master_license or self.pkg_licenses:
            # restrict that matches iff the licenses are allowed
            restrict = delegate(partial(self._apply_license_filter, master_license))
            filters.append(restrict)

        return tuple(filters)

    @klass.jit_attr_none
    def _default_licenses_manager(self):
        return OverlayedLicenses(*self.source_repos_raw)

    def _apply_license_filter(self, master_licenses, pkg, mode):
        """Determine if a package's license is allowed."""
        # note we're not honoring mode; it's always match.
        # reason is that of not turning on use flags to get acceptable license
        # pairs, maybe change this down the line?

        matched_pkg_licenses = []
        for atom, licenses in self.pkg_licenses:
            if atom.match(pkg):
                matched_pkg_licenses += licenses

        raw_accepted_licenses = master_licenses + matched_pkg_licenses
        license_manager = getattr(pkg.repo, 'licenses', self._default_licenses_manager)

        for and_pair in pkg.license.dnf_solutions():
            accepted = incremental_expansion_license(
                pkg, and_pair, license_manager.groups, raw_accepted_licenses,
                msg_prefix=f"while checking ACCEPT_LICENSE ")
            if accepted.issuperset(and_pair):
                return True
        return False

    def _make_keywords_filter(self, default_keys, accept_keywords, incremental=False):
        """Generates a restrict that matches iff the keywords are allowed."""
        if not accept_keywords and not self.profile.keywords:
            return packages.PackageRestriction(
                "keywords", values.ContainmentMatch2(frozenset(default_keys)))

        if self.unstable_arch not in default_keys:
            # stable; thus empty entries == ~arch
            def f(r, v):
                if not v:
                    return r, self.unstable_arch
                return r, v
            data = collapsed_restrict_to_data(
                ((packages.AlwaysTrue, default_keys),),
                (f(*i) for i in accept_keywords))
        else:
            if incremental:
                f = collapsed_restrict_to_data
            else:
                f = non_incremental_collapsed_restrict_to_data
            data = f(((packages.AlwaysTrue, default_keys),), accept_keywords)

        if incremental:
            raise NotImplementedError(self._incremental_apply_keywords_filter)
            #f = self._incremental_apply_keywords_filter
        else:
            f = self._apply_keywords_filter
        return delegate(partial(f, data))

    @staticmethod
    def _incremental_apply_keywords_filter(data, pkg, mode):
        # note we ignore mode; keywords aren't influenced by conditionals.
        # note also, we're not using a restriction here.  this is faster.
        allowed = data.pull_data(pkg)
        return any(True for x in pkg.keywords if x in allowed)

    def _apply_keywords_filter(self, data, pkg, mode):
        # note we ignore mode; keywords aren't influenced by conditionals.
        # note also, we're not using a restriction here.  this is faster.
        pkg_keywords = pkg.keywords
        for atom, keywords in self.profile.keywords:
            if atom.match(pkg):
                pkg_keywords += keywords
        allowed = data.pull_data(pkg)
        if '**' in allowed:
            return True
        if "*" in allowed:
            for k in pkg_keywords:
                if k[0] not in "-~":
                    return True
        if "~*" in allowed:
            for k in pkg_keywords:
                if k[0] == "~":
                    return True
        return any(True for x in pkg_keywords if x in allowed)

    @klass.jit_attr_none
    def use_expand_re(self):
        return re.compile(
            "^(?:[+-])?(%s)_(.*)$" %
            "|".join(x.lower() for x in self.profile.use_expand))

    def _split_use_expand_flags(self, use_stream):
        stream = ((self.use_expand_re.match(x), x) for x in use_stream)
        flags, ue_flags = predicate_split(bool, stream, itemgetter(0))
        return list(map(itemgetter(1), flags)), [(x[0].groups(), x[1]) for x in ue_flags]

    def get_package_use_unconfigured(self, pkg, for_metadata=True):
        """Determine use flags for a given package.

        Roughly, this should result in the following, evaluated l->r: non
        USE_EXPAND; profiles, pkg iuse, global configuration, package.use
        configuration, commandline?  stack profiles + pkg iuse; split it into
        use and use_expanded use; do global configuration + package.use
        configuration overriding of non-use_expand use if global configuration
        has a setting for use_expand.

        Args:
            pkg: package object
            for_metadata (bool): if True, we're doing use flag retrieval for
                metadata generation; otherwise, we're just requesting the raw use flags

        Returns:
            Three groups of use flags for the package in the following order:
            immutable flags, enabled flags, and disabled flags.
        """
        pre_defaults = [x[1:] for x in pkg.iuse if x[0] == '+']
        if pre_defaults:
            pre_defaults, ue_flags = self._split_use_expand_flags(pre_defaults)
            pre_defaults.extend(
                x[1] for x in ue_flags if x[0][0].upper() not in self.settings)

        attr = 'stable_' if self.stable_arch in pkg.keywords \
            and self.unstable_arch not in self.settings['ACCEPT_KEYWORDS'] else ''
        disabled = getattr(self.profile, attr + 'masked_use').pull_data(pkg)
        immutable = getattr(self, attr + 'forced_use').pull_data(pkg)

        # lock the configurable use flags to only what's in IUSE, and what's forced
        # from the profiles (things like userland_GNU and arch)
        enabled = self.enabled_use.pull_data(pkg, pre_defaults=pre_defaults)

        # support globs for USE_EXPAND vars
        use_globs = [u for u in enabled if u.endswith('*')]
        enabled_use_globs = []
        for glob in use_globs:
            for u in pkg.iuse_stripped:
                if u.startswith(glob[:-1]):
                    enabled_use_globs.append(u)
        enabled.difference_update(use_globs)
        enabled.update(enabled_use_globs)

        if for_metadata:
            preserves = pkg.iuse_stripped
            enabled.intersection_update(preserves)
            enabled.update(immutable)
            enabled.difference_update(disabled)

        return immutable, enabled, disabled

    def get_package_domain(self, pkg):
        """Get domain object with altered settings from matching package.env entries."""
        if getattr(pkg, '_domain', None) is not None:
            return pkg._domain

        files = []
        for restrict, paths in self.pkg_env:
            if restrict.match(pkg):
                files.extend(paths)
        if files:
            pkg_settings = dict(self._settings.orig.items())
            for path in files:
                PortageConfig.load_make_conf(
                    pkg_settings, path, allow_sourcing=True,
                    allow_recurse=False, incrementals=True)

            # TODO: Improve pkg domain vs main domain proxying, e.g. static
            # jitted attrs should always be generated and pulled from the main
            # domain obj; however, currently each pkg domain instance gets its
            # own copy so values collapsed on the pkg domain instance aren't
            # propagated back to the main domain leading to regen per pkg if
            # requested.
            pkg_domain = copy.copy(self)
            pkg_domain._settings = ProtectedDict(pkg_settings)
            # reset jitted attrs that can pull updated settings
            for attr in (x for x in dir(self) if x.startswith('_jit_reset_')):
                setattr(pkg_domain, attr, None)
            # store altered domain on the pkg obj to avoid recreating pkg domain
            object.__setattr__(pkg, "_domain", pkg_domain)
            return pkg_domain
        return self

    def get_package_bashrcs(self, pkg):
        for source in self.profile.bashrcs:
            yield source
        for source in self.bashrcs:
            yield source
        if not os.path.exists(self.ebuild_hook_dir):
            return
        # matching portage behavior... it's whacked.
        base = pjoin(self.ebuild_hook_dir, pkg.category)
        dirs = (
            pkg.package,
            f"{pkg.package}:{pkg.slot}",
            getattr(pkg, "P", None),
            getattr(pkg, "PF", None),
        )
        for fp in filter(None, dirs):
            fp = pjoin(base, fp)
            if os.path.exists(fp):
                yield local_source(fp)

    def _wrap_repo(self, repo, filtered=True):
        """Create a filtered, wrapped repo object for the domain."""
        wrapped_repo = self._configure_repo(repo)
        if filtered:
            wrapped_repo = self.filter_repo(wrapped_repo)
        return wrapped_repo

    def add_repo(self, path, config, name=None, configure=True):
        """Add an external repo to the domain."""
        path = os.path.abspath(path)
        # don't recreate existing repos
        for repo in self.source_repos_raw:
            if repo.location == path:
                return repo
        try:
            # forcibly create repo_config object, otherwise cached version might be used
            repo_config = RepoConfig(path, disable_inst_caching=True)
        except OSError as e:
            raise repo_errors.InvalidRepo(str(e))
        kwargs = {}
        if repo_config.cache_format is not None:
            # default to using md5 cache
            kwargs['cache'] = (md5_cache(path),)
        repo_obj = ebuild_repo.tree(config, repo_config, **kwargs)
        self.source_repos_raw += repo_obj

        # reset repo-related jit attrs
        for attr in (x for x in dir(self) if x.startswith('_jit_repo_')):
            setattr(self, attr, None)

        if configure:
            return self._wrap_repo(repo_obj)
        return repo_obj

    def find_repo(self, path, config, configure=True):
        """Find and add an external repo to the domain given a path."""
        repo = None
        path = os.path.abspath(path)
        with suppress_logging():
            while True:
                try:
                    repo = self.add_repo(path, config=config, configure=configure)
                    break
                except repo_errors.InvalidRepo:
                    parent = os.path.dirname(path)
                    if parent == path:
                        break
                    path = parent
        return repo

    def _configure_repo(self, repo):
        """Configure a raw repo."""
        configured_repo = repo
        if not repo.configured:
            pargs = [repo]
            try:
                for x in repo.configurables:
                    if x == "domain":
                        pargs.append(self)
                    elif x == "settings":
                        pargs.append(self.settings)
                    elif x == "profile":
                        pargs.append(self.profile)
                    else:
                        pargs.append(getattr(self, x))
            except AttributeError as e:
                raise Failure(
                    f"failed configuring repo {repo!r}: "
                    f"configurable missing: {e}") from e
            configured_repo = repo.configure(*pargs)
        return configured_repo

    def filter_repo(self, repo, pkg_masks=None, pkg_unmasks=None, pkg_filters=None,
                    pkg_accept_keywords=None, pkg_keywords=None, profile=True):
        """Filter a configured repo."""
        if pkg_masks is None:
            pkg_masks = self.pkg_masks
        if pkg_unmasks is None:
            pkg_unmasks = self.pkg_unmasks
        if pkg_filters is None:
            pkg_filters = self._pkg_filters(pkg_accept_keywords, pkg_keywords)

        global_masks = [((), repo.pkg_masks)]
        if profile:
            global_masks.extend(self.profile._incremental_masks)
        masks = set()
        for neg, pos in global_masks:
            masks.difference_update(neg)
            masks.update(pos)
        masks.update(pkg_masks)
        unmasks = set()
        if profile:
            for neg, pos in self.profile._incremental_unmasks:
                unmasks.difference_update(neg)
                unmasks.update(pos)
        unmasks.update(pkg_unmasks)

        filters = generate_filter(masks, unmasks, *pkg_filters)
        return filtered.tree(repo, filters, True)

    @klass.jit_attr_named('_jit_reset_tmpdir', uncached_val=None)
    def tmpdir(self):
        """Temporary directory for the system.

        Uses PORTAGE_TMPDIR setting and falls back to using the system's TMPDIR if unset.
        """
        path = self.settings.get('PORTAGE_TMPDIR', '')
        if not os.path.exists(path):
            try:
                os.mkdir(path)
            except EnvironmentError:
                path = tempfile.gettempdir()
                logger.warning(f'nonexistent PORTAGE_TMPDIR path, defaulting to {path!r}')
        return os.path.normpath(path)

    @property
    def pm_tmpdir(self):
        """Temporary directory for the package manager."""
        return pjoin(self.tmpdir, 'portage')

    @property
    def repo_configs(self):
        """All defined repo configs."""
        return tuple(r.config for r in self.repos if hasattr(r, 'config'))

    @klass.jit_attr
    def KV(self):
        """The version of the running kernel."""
        ret, version = spawn_get_output(['uname', '-r'])
        if ret == 0:
            return version[0].strip()
        raise ValueError('unknown kernel version')

    @klass.jit_attr_named('_jit_repo_source_repos_raw', uncached_val=None)
    def source_repos_raw(self):
        """Group of package repos without filtering."""
        repos = []
        for r in self.__repos:
            try:
                repo = r.instantiate()
                if not repo.is_supported:
                    logger.warning(
                        f'skipping {r.name!r} repo: unsupported EAPI {str(repo.eapi)!r}')
                    continue
                repos.append(repo)
            except config_errors.InstantiationError as e:
                # roll back the exception chain to a meaningful error message
                exc = find_user_exception(e)
                if exc is None:
                    exc = e
                logger.warning(f'skipping {r.name!r} repo: {exc}')
        return RepositoryGroup(repos)

    @klass.jit_attr_named('_jit_repo_installed_repos_raw', uncached_val=None)
    def installed_repos_raw(self):
        """Group of installed repos without filtering."""
        repos = [r.instantiate() for r in self.__vdb]
        if self.profile.provides_repo is not None:
            repos.append(self.profile.provides_repo)
        return RepositoryGroup(repos)

    @klass.jit_attr_named('_jit_repo_repos_raw', uncached_val=None)
    def repos_raw(self):
        """Group of all repos without filtering."""
        return RepositoryGroup(
            chain(self.source_repos_raw, self.installed_repos_raw))

    @klass.jit_attr_named('_jit_repo_source_repos', uncached_val=None)
    def source_repos(self):
        """Group of configured, filtered package repos."""
        repos = []
        for repo in self.source_repos_raw:
            try:
                repos.append(self._wrap_repo(repo, filtered=True))
            except repo_errors.RepoError as e:
                logger.warning(f'skipping {repo.repo_id!r} repo: {e}')
        return RepositoryGroup(repos)

    @klass.jit_attr_named('_jit_repo_installed_repos', uncached_val=None)
    def installed_repos(self):
        """Group of configured, installed package repos."""
        repos = []
        for repo in self.installed_repos_raw:
            try:
                repos.append(self._wrap_repo(repo, filtered=False))
            except repo_errors.RepoError as e:
                logger.warning(f'skipping {repo.repo_id!r} repo: {e}')
        return RepositoryGroup(repos)

    @klass.jit_attr_named('_jit_repo_unfiltered_repos', uncached_val=None)
    def unfiltered_repos(self):
        """Group of all configured repos without filtering."""
        repos = chain(self.source_repos, self.installed_repos)
        return RepositoryGroup(
            (r.raw_repo if r.raw_repo is not None else r) for r in repos)

    @klass.jit_attr_named('_jit_repo_repos', uncached_val=None)
    def repos(self):
        """Group of all repos."""
        return RepositoryGroup(
            chain(self.source_repos, self.installed_repos))

    @klass.jit_attr_named('_jit_repo_ebuild_repos', uncached_val=None)
    def ebuild_repos(self):
        """Group of all ebuild repos bound with configuration data."""
        return RepositoryGroup(
            x for x in self.source_repos
            if isinstance(x.raw_repo, ebuild_repo.ConfiguredTree))

    @klass.jit_attr_named('_jit_repo_ebuild_repos_unfiltered', uncached_val=None)
    def ebuild_repos_unfiltered(self):
        """Group of all ebuild repos without package filtering."""
        return RepositoryGroup(
            x for x in self.unfiltered_repos
            if isinstance(x, ebuild_repo.ConfiguredTree))

    @klass.jit_attr_named('_jit_repo_ebuild_repos_raw', uncached_val=None)
    def ebuild_repos_raw(self):
        """Group of all ebuild repos without filtering."""
        return RepositoryGroup(
            x for x in self.source_repos_raw
            if isinstance(x, ebuild_repo.UnconfiguredTree))

    @klass.jit_attr_named('_jit_repo_binary_repos', uncached_val=None)
    def binary_repos(self):
        """Group of all binary repos bound with configuration data."""
        return RepositoryGroup(
            x for x in self.source_repos
            if isinstance(x.raw_repo, binary_repo.ConfiguredTree))

    @klass.jit_attr_named('_jit_repo_binary_repos_unfiltered', uncached_val=None)
    def binary_repos_unfiltered(self):
        """Group of all binary repos without package filtering."""
        return RepositoryGroup(
            x for x in self.unfiltered_repos
            if isinstance(x, binary_repo.ConfiguredTree))

    @klass.jit_attr_named('_jit_repo_binary_repos_raw', uncached_val=None)
    def binary_repos_raw(self):
        """Group of all binary repos without filtering."""
        return RepositoryGroup(
            x for x in self.source_repos_raw
            if isinstance(x, binary_repo.tree))

    # multiplexed repos
    all_repos = klass.alias_attr("repos.combined")
    all_repos_raw = klass.alias_attr("repos_raw.combined")
    all_source_repos = klass.alias_attr("source_repos.combined")
    all_source_repos_raw = klass.alias_attr("source_repos_raw.combined")
    all_installed_repos = klass.alias_attr("installed_repos.combined")
    all_installed_repos_raw = klass.alias_attr("installed_repos_raw.combined")
    all_unfiltered_repos = klass.alias_attr("unfiltered_repos.combined")
    all_ebuild_repos = klass.alias_attr("ebuild_repos.combined")
    all_ebuild_repos_unfiltered = klass.alias_attr("ebuild_repos_unfiltered.combined")
    all_ebuild_repos_raw = klass.alias_attr("ebuild_repos_raw.combined")
    all_binary_repos = klass.alias_attr("binary_repos.combined")
    all_binary_repos_unfiltered = klass.alias_attr("binary_repos_unfiltered.combined")
    all_binary_repos_raw = klass.alias_attr("binary_repos_raw.combined")
