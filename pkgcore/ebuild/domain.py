# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
gentoo configuration domain
"""

__all__ = ("MissingFile", "Failure", "domain")

# XXX doc this up better...

from itertools import izip, imap
import os.path

import pkgcore.config.domain
from pkgcore.config import ConfigHint
from pkgcore.restrictions.delegated import delegate
from pkgcore.restrictions import packages, values
from pkgcore.ebuild.atom import generate_collapsed_restriction
from pkgcore.repository import multiplex, visibility
from snakeoil.data_source import local_source
from pkgcore.config.errors import BaseError
from pkgcore.ebuild import const
from pkgcore.ebuild.misc import (collapsed_restrict_to_data,
    non_incremental_collapsed_restrict_to_data, incremental_expansion,
    incremental_expansion_license, optimize_incrementals,
    restrict_payload, ChunkedDataDict, chunked_data, split_negations)
from pkgcore.ebuild.repo_objs import OverlayedLicenses
from pkgcore.util.parserestrict import parse_match

from snakeoil.lists import stable_unique, unstable_unique, predicate_split
from snakeoil.compatibility import any, raise_from
from snakeoil.mappings import ProtectedDict
from snakeoil.fileutils import iter_read_bash
from snakeoil.currying import partial
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin
demandload(globals(),
    'errno',
    'pkgcore.fs.livefs:iter_scan',
    'pkgcore.fs.fs:fsFile',
    're',
    'operator:itemgetter',
    'pkgcore.ebuild.triggers:generate_triggers@ebuild_generate_triggers',
)

class MissingFile(BaseError):
    def __init__(self, filename, setting):
        BaseError.__init__(self,
                               "setting %s points at %s, which doesn't exist."
                               % (setting, filename))
        self.file, self.setting = filename, setting

class Failure(BaseError):
    def __init__(self, text):
        BaseError.__init__(self, "domain failure: %s" % (text,))
        self.text = text


def package_keywords_splitter(val):
    v = val.split()
    return parse_match(v[0]), stable_unique(v[1:])

def package_env_splitter(basedir, val):
    val = val.split()
    return parse_match(val[0]), local_source(pjoin(basedir, val[1]))


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
#
# note also, that this is rather ebuild centric. it shouldn't be, and
# should be redesigned to be a seperation of configuration
# instantiation manglers, and then the ebuild specific chunk (which is
# selected by config)
# ~harring


def generate_masking_restrict(masks):
    # if it's masked, it's not a match
    return generate_collapsed_restriction(masks, negate=True)

def generate_unmasking_restrict(unmasks):
    return generate_collapsed_restriction(unmasks)


class domain(pkgcore.config.domain.domain):

    # XXX ouch, verify this crap and add defaults and stuff
    _types = {
        'profile': 'ref:profile', 'fetcher': 'ref:fetcher',
        'repositories': 'lazy_refs:repo', 'vdb': 'lazy_refs:repo',
        'name': 'str', 'triggers':'lazy_refs:trigger',
        }
    for _thing in list(const.incrementals) + ['bashrc']:
        _types[_thing] = 'list'
    for _thing in [
        'package.mask', 'package.keywords', 'package.license', 'package.use',
        'package.unmask', 'package.env']:
        _types[_thing] = 'list'
    for _thing in ['root', 'CHOST', 'CBUILD', 'CTARGET', 'CFLAGS', 'PATH',
        'PORTAGE_TMPDIR', 'DISTCC_PATH', 'DISTCC_DIR', 'CCACHE_DIR']:
        _types[_thing] = 'str'

    # TODO this is missing defaults
    pkgcore_config_type = ConfigHint(
            _types, typename='domain',
            required=['repositories', 'profile', 'vdb', 'fetcher', 'name'],
            allow_unknowns=True)

    del _types, _thing

    def __init__(self, profile, repositories, vdb, name=None,
        root='/', incrementals=const.incrementals, triggers=(), **settings):
        # voodoo, unfortunately (so it goes)
        # break this up into chunks once it's stabilized (most of code
        # here has already, but still more to add)
        self._triggers = triggers
        if 'CHOST' in settings and 'CBUILD' not in settings:
            settings['CBUILD'] = settings['CHOST']
        settings.setdefault('ACCEPT_LICENSE', const.ACCEPT_LICENSE)

        # map out sectionname -> config manager immediately.
        repositories_collapsed = [r.collapse() for r in repositories]
        repositories = [r.instantiate() for r in repositories_collapsed]

        self.fetcher = settings.pop("fetcher")

        self.default_licenses_manager = OverlayedLicenses(*repositories)
        vdb_collapsed = [r.collapse() for r in vdb]
        vdb = [r.instantiate() for r in vdb_collapsed]
        self.named_repos = dict(
            (collapsed.name, repo) for (collapsed, repo) in izip(
                repositories_collapsed, repositories))
        self.named_repos.update(
            (collapsed.name, repo) for (collapsed, repo) in izip(
                vdb_collapsed, vdb))
        self.named_repos.pop(None, None)
        if profile.provides_repo is not None:
            self.named_repos['package.provided'] = profile.provides_repo
            vdb.append(profile.provides_repo)

        self.profile = profile
        pkg_maskers = set(profile.masks)
        for r in repositories:
            pkg_maskers.update(r.default_visibility_limiters)
        pkg_maskers = list(pkg_maskers)
        pkg_unmaskers, pkg_keywords, pkg_license = [], [], []
        pkg_use, self.bashrcs = [], []

        self.ebuild_hook_dir = settings.pop("ebuild_hook_dir", None)

        for key, val, action in (
            ("package.mask", pkg_maskers, parse_match),
            ("package.unmask", pkg_unmaskers, parse_match),
            ("package.keywords", pkg_keywords, package_keywords_splitter),
            ("package.license", pkg_license, package_keywords_splitter),
            ("package.use", pkg_use, package_keywords_splitter),
            ("package.env", self.bashrcs, package_env_splitter),
            ):

            for fp in settings.pop(key, ()):
                try:
                    if key == "package.env":
                        base = self.ebuild_hook_dir
                        if base is None:
                            base = os.path.dirname(fp)
                        action = partial(action, base)
                    for fs_obj in iter_scan(fp, follow_symlinks=True):
                        if not fs_obj.is_reg or '/.' in fs_obj.location:
                            continue
                        val.extend(action(x) for x in iter_read_bash(fs_obj.location))
                except EnvironmentError, e:
                    if e.errno == errno.ENOENT:
                        raise MissingFile(fp, key)
                    raise_from(Failure("failed reading '%s': %s" % (fp, e)))
                except ValueError, e:
                    raise_from(Failure("failed reading '%s': %s" % (fp, e)))

        self.name = name
        settings.setdefault("PKGCORE_DOMAIN", name)
        for x in incrementals:
            if isinstance(settings.get(x), basestring):
                settings[x] = tuple(settings[x].split())

        # roughly... all incremental stacks should be interpreted left -> right
        # as such we start with the profile settings, and append ours onto it.
        for k, v in profile.default_env.iteritems():
            if k not in settings:
                settings[k] = v
                continue
            if k in incrementals:
                settings[k] = v + tuple(settings[k])

        # next we finalize incrementals.
        for incremental in incrementals:
            # skip USE for the time being; hack; we need the negations currently
            # so that pkg iuse induced enablings can be disabled by negations.
            # think of the profile doing USE=-cdr for brasero w/ IUSE=+cdr
            # for example
            if incremental not in settings or incremental == "USE":
                continue
            s = set()
            incremental_expansion(s, settings[incremental])
            settings[incremental] = tuple(s)

        # use is collapsed; now stack use_expand.
        use = settings['USE'] = set(optimize_incrementals(
            settings.get("USE", ())))

        # hackish implementation; if test is on, flip on the flag
        if "test" in settings.get("FEATURES", ()):
            use.add("test")

        self.use_expand = frozenset(profile.use_expand)
        self.use_expand_hidden = frozenset(profile.use_expand_hidden)
        for u in profile.use_expand:
            v = settings.get(u)
            if v is None:
                continue
            u2 = u.lower()+"_"
            use.update(u2 + x for x in v.split())

        # visibility mask...
        # if ((package.mask or visibility) and not package.unmask)
        # or not (package.keywords or accept_keywords)
        vfilter = packages.AndRestriction(finalize=False,
            disable_inst_caching=True)
        r = None
        if pkg_maskers:
            r = generate_masking_restrict(pkg_maskers)
        if pkg_unmaskers:
            if r is None:
                # unmasking without masking... 'k (wtf?)
                r = generate_unmasking_restrict(pkg_unmaskers)
            else:
                r = packages.OrRestriction(
                    r, generate_unmasking_restrict(pkg_unmaskers),
                    disable_inst_caching=True)
        if r:
            vfilter.add_restriction(r)
        del pkg_unmaskers, pkg_maskers

        license, default_keywords = [], []
        master_license = []
        if not 'ACCEPT_KEYWORDS' in settings:
            raise Failure("No ACCEPT_KEYWORDS setting detected from profile, "
                          "or user config")
        s = set()
        incremental_expansion(s, settings['ACCEPT_KEYWORDS'],
            'while expanding ACCEPT_KEYWORDS')
        default_keywords.extend(s)
        settings['ACCEPT_KEYWORDS'] = default_keywords

        master_license.extend(settings.get('ACCEPT_LICENSE', ()))

        self.use = use

        if "ARCH" not in settings:
            raise Failure(
                "No ARCH setting detected from profile, or user config")

        self.arch = settings["ARCH"]

        # ~amd64 -> [amd64, ~amd64]
        for x in default_keywords[:]:
            if x.startswith("~"):
                default_keywords.append(x.lstrip("~"))
        default_keywords = unstable_unique(default_keywords + [self.arch])

        vfilter.add_restriction(self.make_keywords_filter(
            self.arch, default_keywords, pkg_keywords,
            incremental="package.keywords" in incrementals))

        del default_keywords
        # we can finally close that fricking
        # "DISALLOW NON FOSS LICENSES" bug via this >:)
        if master_license:
            vfilter.add_restriction(self.make_license_filter(
                master_license, license))

        del master_license, license

        vfilter.finalize()

        # if it's made it this far...

        self.root = settings["ROOT"] = root
        self.settings = settings

        for data in self.settings.get('bashrc', ()):
            source = local_source(data)
            # this is currently local-only so a path check is ok
            # TODO make this more general
            if not os.path.exists(source.path):
                raise Failure(
                    'user-specified bashrc %r does not exist' % (data,))
            self.bashrcs.append((packages.AlwaysTrue, source))

        # stack use stuff first, then profile.
        self.enabled_use = ChunkedDataDict()
        self.enabled_use.merge(profile.pkg_use)
        self.enabled_use.add_bare_global(*split_negations(self.use))
        self.enabled_use.update_from_stream(chunked_data(k, *split_negations(v)) for k,v in pkg_use)
        self.enabled_use.add_bare_global((), (self.arch,))
        self.forced_use = ChunkedDataDict()
        self.forced_use.merge(profile.forced_use)
        self.forced_use.add_bare_global((), (self.arch,))
        self.disabled_use = ChunkedDataDict()
        self.disabled_use.merge(profile.masked_use)

        self.settings = ProtectedDict(settings)
        self.repos = []
        self.vdb = []
        self.configured_named_repos = {}
        self.filtered_named_repos = {}

        rev_names = dict((repo, name) for name, repo in self.named_repos.iteritems())


        for l, repos, filtered in ((self.repos, repositories, True),
            (self.vdb, vdb, False)):

            for repo in repos:
                if not repo.configured:
                    pargs = [repo]
                    try:
                        for x in repo.configurables:
                            if x == "domain":
                                pargs.append(self)
                            elif x == "settings":
                                pargs.append(settings)
                            elif x == "profile":
                                pargs.append(profile)
                            else:
                                pargs.append(getattr(self, x))
                    except AttributeError, ae:
                        raise_from(Failure("failed configuring repo '%s': "
                                      "configurable missing: %s" % (repo, ae)))
                    wrapped_repo = repo.configure(*pargs)
                else:
                    wrapped_repo = repo
                key = rev_names.get(repo)
                self.configured_named_repos[key] = wrapped_repo
                if filtered:
                    wrapped_repo = visibility.filterTree(wrapped_repo,
                        vfilter, True)
                self.filtered_named_repos[key] = wrapped_repo
                l.append(wrapped_repo)

        if profile.virtuals:
            l = [x for x in (getattr(v, 'old_style_virtuals', None)
                for v in self.vdb) if x is not None]
            profile_repo = profile.make_virtuals_repo(
                multiplex.tree(*repositories), *l)
            self.named_repos["profile virtuals"] = profile_repo
            self.filtered_named_repos["profile virtuals"] = profile_repo
            self.configured_named_repos["profile virtuals"] = profile_repo
            self.repos = [profile_repo] + self.repos

        self.use_expand_re = re.compile("^(?:[+-])?(%s)_(.*)$" %
            "|".join(x.lower() for x in sorted(self.use_expand, reverse=True)))

    def make_license_filter(self, master_license, pkg_licenses):
#        data = collapsed_restrict_to_data(
#            ((packages.AlwaysTrue, master_license),),
#            pkg_licenses)
#        return delegate(partial(self.apply_license_filter, data))
        return delegate(partial(self.apply_license_filter, master_license,
            pkg_licenses))

    def apply_license_filter(self, master_licenses, pkg_licenses, pkg, mode):
        # note we're not honoring mode; it's always match.
        # reason is that of not turning on use flags to get acceptible license
        # pairs.
        # maybe change this down the line?
        raw_accepted_licenses = master_licenses + pkg_licenses
        license_manager = getattr(pkg.repo, 'licenses', self.default_licenses_manager)
        for and_pair in pkg.license.dnf_solutions():
            accepted = incremental_expansion_license(and_pair, license_manager.groups,
                raw_accepted_licenses,
                msg_prefix="while checking ACCEPT_LICENSE for %s" % (pkg,))
            if accepted.issuperset(and_pair):
                return True
        return False


    def make_keywords_filter(self, arch, default_keys, pkg_keywords,
        incremental=False):
        """Generates a restrict that matches iff the keywords are allowed."""
        if not pkg_keywords:
            return packages.PackageRestriction(
                "keywords", values.ContainmentMatch(*default_keys))

        if "~" + arch.lstrip("~") not in default_keys:
            # stable; thus empty entries == ~arch
            unstable = "~" + arch
            def f(r, v):
                if not v:
                    return r, unstable
                return r, v
            data = collapsed_restrict_to_data(
                ((packages.AlwaysTrue, default_keys),),
                (f(*i) for i in pkg_keywords))
        else:
            if incremental:
                f = collapsed_restrict_to_data
            else:
                f = non_incremental_collapsed_restrict_to_data
            data = f(((packages.AlwaysTrue, default_keys),),
                pkg_keywords)

        if incremental:
            raise NotImplementedError(self.incremental_apply_keywords_filter)
            #f = self.incremental_apply_keywords_filter
        else:
            f = self.apply_keywords_filter
        return delegate(partial(f, data))

    @staticmethod
    def incremental_apply_keywords_filter(data, pkg, mode):
        # note we ignore mode; keywords aren't influenced by conditionals.
        # note also, we're not using a restriction here.  this is faster.
        allowed = data.pull_data(pkg)
        return any(True for x in pkg.keywords if x in allowed)

    @staticmethod
    def apply_keywords_filter(data, pkg, mode):
        # note we ignore mode; keywords aren't influenced by conditionals.
        # note also, we're not using a restriction here.  this is faster.
        allowed = data.pull_data(pkg)
        if '**' in allowed:
            return True
        if "*" in allowed:
            for k in pkg.keywords:
                if k[0] not in "-~":
                    return True
        if "~*" in allowed:
            for k in pkg.keywords:
                if k[0] == "~":
                    return True
        return any(True for x in pkg.keywords if x in allowed)

    def split_use_expand_flags(self, use_stream):
        matcher = self.use_expand_re.match
        stream = ((matcher(x), x) for x in use_stream)
        flags, ue_flags = predicate_split(bool, stream, itemgetter(0))
        return map(itemgetter(1), flags), [(x[0].groups(), x[1]) for x in ue_flags]

    def get_package_use_unconfigured(self, pkg, for_metadata=True):
        # roughly, this alog should result in the following, evaluated l->r
        # non USE_EXPAND; profiles, pkg iuse, global configuration, package.use configuration, commandline?
        # stack profiles + pkg iuse; split it into use and use_expanded use;
        # do global configuration + package.use configuration overriding of non-use_expand use
        # if global configuration has a setting for use_expand,

        pre_defaults = [x[1:] for x in pkg.iuse if x[0] == '+']
        if pre_defaults:
            pre_defaults, ue_flags = self.split_use_expand_flags(pre_defaults)
#            pre_defaults = izip(imap(self.use_expand_re.match, pre_defaults), pre_defaults)
#            flags, ue_flags = predicate_split(bool, pre_defaults, itemgetter(0))
            pre_defaults.extend(x[1]
                for x in ue_flags if x[0][0].upper() not in self.settings)

        # lock the configurable use flags to only what's in IUSE, and what's forced
        # from the profiles (things like userland_GNU and arch)
        enabled = self.enabled_use.pull_data(pkg,
            pre_defaults=pre_defaults)
        if for_metadata:
            enabled = enabled.intersection(x.lstrip("-+") for x in pkg.iuse)

        disabled = self.disabled_use.pull_data(pkg)
        immutable = self.forced_use.pull_data(pkg)

        if disabled:
            pass
            #if enabled is self.enabled_use.defaults:
            #    enabled = set(enabled)
            #if immutable is self.forced_use.defaults:
            #    immutable = set(immutable)
        elif immutable:
            pass
            #if enabled is self.enabled_use.defaults:
            #    enabled = set(enabled)
        else:
            return immutable, enabled, disabled
        enabled.update(immutable)
        enabled.difference_update(disabled)
        immutable.update(disabled)

        return immutable, enabled, disabled

    def get_package_use_buildable(self, pkg):
        # we append USE_EXPAND flags into the build env;
        # this is done for things like linguas.
        changed_use = set(pkg.use)
        immutable, enabled, disabled = self.get_package_use_unconfigured(pkg)
        new_enabled = enabled.difference(changed_use)
        new_disabled = changed_use.difference(enabled)
        # we've isolated what's changed.  now get the buildable use,
        # and apply those changes
        immutable, enabled, disabled = self.get_package_use_unconfigured(pkg,
            for_metadata=False)
        enabled.update(new_enabled)
        enabled.difference_update(new_disabled)
        return enabled

    def get_package_bashrcs(self, pkg):
        for source in self.profile.bashrcs:
            yield source
        for restrict, source in self.bashrcs:
            if restrict.match(pkg):
                yield source
        if not self.ebuild_hook_dir:
            return
        # matching portage behaviour... it's whacked.
        base = pjoin(self.ebuild_hook_dir, pkg.category)
        for fp in (pkg.package, "%s:%s" % (pkg.package, pkg.slot),
            getattr(pkg, "P", "nonexistant"), getattr(pkg, "PF", "nonexistant")):
            fp = pjoin(base, fp)
            if os.path.exists(fp):
                yield local_source(fp)

    def _mk_nonconfig_triggers(self):
        return ebuild_generate_triggers(self)

    def _get_tempspace(self):
        path = self.settings.get("PORTAGE_TMPDIR", None)
        if path is not None:
            path = pjoin(path, 'portage')
        return path
