# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
gentoo configuration domain
"""

__all__ = ("domain",)

# XXX doc this up better...

from functools import partial, wraps
from itertools import chain, izip, ifilter, imap
import os.path

from snakeoil import klass
from snakeoil.bash import iter_read_bash
from snakeoil.compatibility import raise_from
from snakeoil.data_source import local_source
from snakeoil.demandload import demandload
from snakeoil.mappings import ProtectedDict, ImmutableDict
from snakeoil.osutils import pjoin
from snakeoil.sequences import (
    split_negations, stable_unique, unstable_unique, predicate_split)

from pkgcore.config import ConfigHint
from pkgcore.config.domain import Failure, MissingFile, domain as config_domain
from pkgcore.ebuild import const
from pkgcore.ebuild.atom import atom as _atom
from pkgcore.ebuild.misc import (
    ChunkedDataDict, chunked_data, collapsed_restrict_to_data,
    incremental_expansion, incremental_expansion_license,
    non_incremental_collapsed_restrict_to_data, optimize_incrementals)
from pkgcore.ebuild.repo_objs import OverlayedLicenses
from pkgcore.repository import filtered
from pkgcore.repository.util import RepositoryGroup
from pkgcore.restrictions import packages, values
from pkgcore.restrictions.delegated import delegate
from pkgcore.util.parserestrict import parse_match, ParseError

demandload(
    'collections:defaultdict',
    'copy',
    'errno',
    'multiprocessing:cpu_count',
    'operator:itemgetter',
    're',
    'tempfile',
    'pkgcore.binpkg:repository@binary_repo',
    'pkgcore.ebuild:repository@ebuild_repo',
    'pkgcore.ebuild.portage_conf:load_make_conf',
    'pkgcore.ebuild.repo_objs:RepoConfig',
    'pkgcore.ebuild.triggers:generate_triggers@ebuild_generate_triggers',
    'pkgcore.fs.livefs:iter_scan,sorted_scan',
    'pkgcore.log:logger',
)


def package_masks(iterable):
    for line, lineno, path in iterable:
        try:
            yield parse_match(line), line, lineno, path
        except ParseError as e:
            logger.warning('%r, line %s: parsing error: %s' % (path, lineno, e))


def package_keywords_splitter(iterable):
    for line, lineno, path in iterable:
        v = line.split()
        try:
            yield parse_match(v[0]), tuple(stable_unique(v[1:])), line, lineno, path
        except ParseError as e:
            logger.warning('%r, line %s: parsing error: %s' % (path, lineno, e))


def package_env_splitter(basedir, iterable):
    for line, lineno, path in iterable:
        val = line.split()
        if len(val) == 1:
            logger.warning("%r, line %s: missing file reference: %r" % (path, lineno, line))
            continue
        paths = []
        for env_file in val[1:]:
            fp = pjoin(basedir, env_file)
            if os.path.exists(fp):
                paths.append(fp)
            else:
                logger.warning("%r, line %s: nonexistent file: %r" % (path, lineno, fp))
        try:
            yield parse_match(val[0]), tuple(paths), line, lineno, path
        except ParseError as e:
            logger.warning('%r, line %s: parsing error: %s' % (path, lineno, e))


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


def load_property(filename, parsing_func=lambda x: x, fallback=()):
    """Decorator simplifying parsing config files to generate a domain property.

    :param filename: The filename to parse within the config directory.
    :keyword parsing_func: An invokable used to parse the data.
    :keyword fallback: What to return if the file does not exist -- must be immutable.
    :return: A :py:`klass.jit.attr_named` property instance.
    """
    def f(func):
        @wraps(func)
        def _load_and_invoke(func, fallback, self):
            data = _read_config_file(pjoin(self.config_dir, filename))
            if data is None:
                data = fallback
            else:
                data = parsing_func(data)
            return func(self, data)
        f2 = klass.jit_attr_named('_jit_%s' % (func.__name__,))
        return f2(partial(_load_and_invoke, func, fallback))
    return f


def _read_config_file(path):
    """Read all the data files under a given path."""
    try:
        for fs_obj in iter_scan(path, follow_symlinks=True):
            if not fs_obj.is_reg or '/.' in fs_obj.location:
                continue
            for lineno, line, in iter_read_bash(
                    fs_obj.location, allow_line_cont=True, enum_line=True):
                yield line, lineno, fs_obj.location
    except EnvironmentError as e:
        if e.errno != errno.ENOENT:
            raise_from(Failure("failed reading %r: %s" % (filename, e)))


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
        'repositories': 'lazy_refs:repo', 'vdb': 'lazy_refs:repo',
        'name': 'str', 'triggers': 'lazy_refs:trigger',
    }
    for _thing in ('root', 'config_dir', 'CHOST', 'CBUILD', 'CTARGET', 'CFLAGS', 'PATH',
                   'PORTAGE_TMPDIR', 'DISTCC_PATH', 'DISTCC_DIR', 'CCACHE_DIR'):
        _types[_thing] = 'str'

    # control adding debug info (line/lineno/path) to config file parsed output
    _debug = False

    # TODO this is missing defaults
    pkgcore_config_type = ConfigHint(
        _types, typename='domain',
        required=['repositories', 'profile', 'vdb', 'fetcher', 'name'],
        allow_unknowns=True)

    del _types, _thing

    def __init__(self, profile, repositories, vdb, name=None,
                 root='/', config_dir='/etc/portage', prefix='/',
                 triggers=(), **settings):
        self._triggers = triggers
        self.name = name
        self.root = settings["ROOT"] = root
        self.config_dir = config_dir
        self.prefix = prefix
        self.ebuild_hook_dir = pjoin(self.config_dir, 'env')
        self.profile = profile
        self.fetcher = settings.pop("fetcher")

        # prevent critical variables from being changed in make.conf
        for k in self.profile.profile_only_variables.intersection(settings.keys()):
            del settings[k]

        # Protect original settings from being overridden so matching
        # package.env settings can be overlaid properly.
        self._settings = ProtectedDict(settings)

        # initialize mutable repo groups
        self.source_repos_raw = RepositoryGroup(r.instantiate() for r in repositories)
        self.installed_repos_raw = RepositoryGroup(r.instantiate() for r in vdb)
        if self.profile.provides_repo is not None:
            self.installed_repos_raw += self.profile.provides_repo

        self.default_licenses_manager = OverlayedLicenses(*self.source_repos_raw)

        self.source_repos = RepositoryGroup()
        self.installed_repos = RepositoryGroup()
        self.unfiltered_repos = RepositoryGroup()

        for repo_group, repos, filtered in (
                (self.source_repos, self.source_repos_raw, True),
                (self.installed_repos, self.installed_repos_raw, False)):
            for repo in repos:
                self.add_repo(repo, filtered=filtered, group=repo_group)

    @klass.jit_attr_named('_jit_reset_settings', uncached_val=None)
    def settings(self):
        settings = self._settings
        if 'CHOST' in settings and 'CBUILD' not in settings:
            settings['CBUILD'] = settings['CHOST']

        # if unset, MAKEOPTS defaults to CPU thread count
        if 'MAKEOPTS' not in settings:
            settings['MAKEOPTS'] = '-j%i' % cpu_count()

        for x in const.incrementals:
            if isinstance(settings.get(x), basestring):
                settings[x] = tuple(settings[x].split())

        # roughly... all incremental stacks should be interpreted left -> right
        # as such we start with the profile settings, and append ours onto it.
        for k, v in self.profile.default_env.iteritems():
            if k not in settings:
                settings[k] = v
                continue
            if k in const.incrementals:
                settings[k] = v + tuple(settings[k])

        # next we finalize incrementals.
        for incremental in const.incrementals:
            # Skip USE/ACCEPT_LICENSE for the time being; hack; we need the
            # negations currently so that pkg iuse induced enablings can be
            # disabled by negations. For example, think of the profile doing
            # USE=-cdr for brasero w/ IUSE=+cdr. Similarly, ACCEPT_LICENSE is
            # skipped because negations are required for license filtering.
            if incremental not in settings or incremental in ("USE", "ACCEPT_LICENSE"):
                continue
            s = set()
            incremental_expansion(
                s, settings[incremental],
                'while expanding %s' % (incremental,))
            settings[incremental] = tuple(s)

        if 'ACCEPT_KEYWORDS' not in settings:
            raise Failure("No ACCEPT_KEYWORDS setting detected from profile, "
                          "or user config")
        s = set()
        default_keywords = []
        incremental_expansion(
            s, settings['ACCEPT_KEYWORDS'],
            'while expanding ACCEPT_KEYWORDS')
        default_keywords.extend(s)
        settings['ACCEPT_KEYWORDS'] = set(default_keywords)

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
        return "~%s" % self.arch

    @klass.jit_attr_named('_jit_reset_use', uncached_val=None)
    def use(self):
        # append expanded use, FEATURES, and environment defined USE flags
        use = list(self.settings.get('USE', ())) + list(self.profile.expand_use(self.settings))

        # hackish implementation; if test is on, flip on the flag
        features = self.settings.get("FEATURES", ())
        if "test" in features:
            use.append("test")
        if "prefix" in features or "force-prefix" in features:
            use.append("prefix")

        use = set(optimize_incrementals(use + os.environ.get('USE', '').split()))
        return use

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
        c = ChunkedDataDict()
        c.merge(getattr(self.profile, 'forced_use'))
        c.add_bare_global((), (self.arch,))
        return c

    @klass.jit_attr_none
    def stable_forced_use(self):
        c = ChunkedDataDict()
        c.merge(getattr(self.profile, 'stable_forced_use'))
        c.add_bare_global((), (self.arch,))
        return c

    @load_property("package.mask", package_masks)
    def pkg_masks(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple(x[0] for x in data)

    @load_property("package.unmask", package_masks)
    def pkg_unmasks(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple(x[0] for x in data)

    # TODO: deprecated, remove in 0.11
    @load_property("package.keywords", package_keywords_splitter)
    def pkg_keywords(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple((x[0], x[1]) for x in data)

    @load_property("package.accept_keywords", package_keywords_splitter)
    def pkg_accept_keywords(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple((x[0], x[1]) for x in data)

    @load_property("package.license", package_keywords_splitter)
    def pkg_licenses(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple((x[0], x[1]) for x in data)

    @load_property("package.use", package_keywords_splitter)
    def pkg_use(self, data):
        if self._debug:
            return tuple(data)
        else:
            return tuple((x[0], split_negations(x[1])) for x in data)

    @load_property("package.env", fallback=None)
    def pkg_env(self, data):
        func = partial(package_env_splitter, self.ebuild_hook_dir)
        data = ifilter(None, func(data))
        if self._debug:
            return tuple(data)
        else:
            return tuple((x[0], x[1]) for x in data)

    @klass.jit_attr
    def bashrcs(self):
        files = sorted_scan(pjoin(self.config_dir, 'bashrc'), follow_symlinks=True)
        return tuple(local_source(x) for x in files)

    @klass.jit_attr_named('_jit_reset_vfilters', uncached_val=None)
    def _vfilters(self):
        # ~amd64 -> [amd64, ~amd64]
        default_keywords = set([self.arch])
        default_keywords.update(self.settings['ACCEPT_KEYWORDS'])
        for x in self.settings['ACCEPT_KEYWORDS']:
            if x.startswith("~"):
                default_keywords.add(x.lstrip("~"))

        # create keyword filters
        accept_keywords = (
            self.pkg_keywords + self.pkg_accept_keywords + self.profile.accept_keywords)
        vfilters = [self._make_keywords_filter(
            default_keywords, accept_keywords,
            incremental="package.keywords" in const.incrementals)]

        # add license filters
        master_license = []
        master_license.extend(self.settings.get('ACCEPT_LICENSE', ()))
        if master_license or self.pkg_licenses:
            # restrict that matches iff the licenses are allowed
            restrict = delegate(partial(self._apply_license_filter, master_license))
            vfilters.append(restrict)

        return tuple(vfilters)

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
        license_manager = getattr(pkg.repo, 'licenses', self.default_licenses_manager)

        for and_pair in pkg.license.dnf_solutions():
            accepted = incremental_expansion_license(
                and_pair, license_manager.groups, raw_accepted_licenses,
                msg_prefix="while checking ACCEPT_LICENSE for %s" % (pkg,))
            if accepted.issuperset(and_pair):
                return True
        return False

    def _make_keywords_filter(self, default_keys, accept_keywords, incremental=False):
        """Generates a restrict that matches iff the keywords are allowed."""
        if not accept_keywords and not self.profile.keywords:
            return packages.PackageRestriction(
                "keywords", values.ContainmentMatch(*default_keys))

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

    @property
    def use_expand_re(self):
        return re.compile(
            "^(?:[+-])?(%s)_(.*)$" %
            "|".join(x.lower() for x in sorted(self.profile.use_expand, reverse=True)))

    def _split_use_expand_flags(self, use_stream):
        stream = ((self.use_expand_re.match(x), x) for x in use_stream)
        flags, ue_flags = predicate_split(bool, stream, itemgetter(0))
        return map(itemgetter(1), flags), [(x[0].groups(), x[1]) for x in ue_flags]

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

    def get_package_use_buildable(self, pkg):
        # isolate just what isn't exposed for metadata- anything non-IUSE
        # this brings in actual use flags the ebuild shouldn't see, but that's
        # a future enhancement to be done when USE_EXPAND is kept separate from
        # mainline USE in this code.

        metadata_use = self.get_package_use_unconfigured(pkg, for_metadata=True)[1]
        raw_use = self.get_package_use_unconfigured(pkg, for_metadata=False)[1]
        enabled = raw_use.difference(metadata_use)

        enabled.update(pkg.use)
        return enabled

    def get_package_domain(self, pkg):
        """Get domain object with altered settings from matching package.env entries."""
        if getattr(pkg, '_domain', None) is not None:
            return pkg._domain

        files = []
        for restrict, paths in self.pkg_env:
            if restrict.match(pkg):
                files.extend(paths)
        if files:
            pkg_settings = dict(self._settings.orig.iteritems())
            for path in files:
                load_make_conf(pkg_settings, path, allow_sourcing=True,
                               allow_recurse=False, incrementals=True)
            pkg_domain = copy.copy(self)
            pkg_domain._settings = ProtectedDict(pkg_settings)
            # reset JIT-ed attrs that can pull updated settings
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
        for fp in (pkg.package, "%s:%s" % (pkg.package, pkg.slot),
                   getattr(pkg, "P", "nonexistent"), getattr(pkg, "PF", "nonexistent")):
            fp = pjoin(base, fp)
            if os.path.exists(fp):
                yield local_source(fp)

    def _mk_nonconfig_triggers(self):
        return ebuild_generate_triggers(self)

    def add_repo(self, repo, filtered=True, group=None, config=None):
        """Add repo to the domain."""
        if group is None:
            group = self.source_repos

        # add unconfigured, external repo to the domain
        # TODO: add support for configuring/enabling the external repo's cache
        if isinstance(repo, basestring):
            if config is None:
                raise ValueError('missing config')
            path = os.path.abspath(repo)
            if not os.path.isdir(os.path.join(path, 'profiles')):
                raise TypeError('invalid repo: %r' % path)
            repo_config = RepoConfig(path, config_name=path)
            repo = ebuild_repo.tree(config, repo_config)
            self.source_repos_raw += repo

        wrapped_repo = self._configure_repo(repo)
        if filtered:
            wrapped_repo = self._filter_repo(wrapped_repo)
        group += wrapped_repo
        return wrapped_repo

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
                raise_from(Failure("failed configuring repo '%s': "
                                   "configurable missing: %s" % (repo, e)))
            configured_repo = repo.configure(*pargs)
        self.unfiltered_repos += configured_repo
        return configured_repo

    def _filter_repo(self, repo):
        """Filter a configured repo."""
        global_masks = chain(repo._masks, self.profile._incremental_masks)
        masks = set()
        for neg, pos in global_masks:
            masks.difference_update(neg)
            masks.update(pos)
        masks.update(self.pkg_masks)
        unmasks = set()
        for neg, pos in self.profile._incremental_unmasks:
            unmasks.difference_update(neg)
            unmasks.update(pos)
        unmasks.update(self.pkg_unmasks)
        filter = generate_filter(masks, unmasks, *self._vfilters)
        filtered_repo = filtered.tree(repo, filter, True)
        return filtered_repo

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
                logger.warning('nonexistent PORTAGE_TMPDIR path, defaulting to %r', path)
        return os.path.normpath(path)

    @property
    def pm_tmpdir(self):
        """Temporary directory for the package manager."""
        return pjoin(self.tmpdir, 'portage')

    @property
    def repo_configs(self):
        """All defined repo configs."""
        return tuple(r.config for r in self.repos if hasattr(r, 'config'))

    @klass.jit_attr_none
    def repos(self):
        """Group of all repos."""
        return RepositoryGroup(
            chain(self.source_repos, self.installed_repos))

    @klass.jit_attr_none
    def repos_raw(self):
        """Group of all repos without filtering."""
        return RepositoryGroup(
            chain(self.source_repos_raw, self.installed_repos_raw))

    @klass.jit_attr_none
    def ebuild_repos(self):
        """Group of all ebuild repos bound with configuration data."""
        return RepositoryGroup(
            x for x in self.source_repos
            if isinstance(x.raw_repo, ebuild_repo._ConfiguredTree))

    @klass.jit_attr_none
    def ebuild_repos_unfiltered(self):
        """Group of all ebuild repos without package filtering."""
        return RepositoryGroup(
            x for x in self.unfiltered_repos
            if isinstance(x, ebuild_repo._ConfiguredTree))

    @klass.jit_attr_none
    def ebuild_repos_raw(self):
        """Group of all ebuild repos without filtering."""
        return RepositoryGroup(
            x for x in self.source_repos_raw
            if isinstance(x, ebuild_repo._UnconfiguredTree))

    @klass.jit_attr_none
    def binary_repos(self):
        """Group of all binary repos bound with configuration data."""
        return RepositoryGroup(
            x for x in self.source_repos
            if isinstance(x.raw_repo, binary_repo.ConfiguredTree))

    @klass.jit_attr_none
    def binary_repos_unfiltered(self):
        """Group of all binary repos without package filtering."""
        return RepositoryGroup(
            x for x in self.unfiltered_repos
            if isinstance(x, binary_repo.ConfiguredTree))

    @klass.jit_attr_none
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
