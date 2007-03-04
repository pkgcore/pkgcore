# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo configuration domain
"""

# XXX doc this up better...

from itertools import izip

import pkgcore.config.domain
from pkgcore.config import ConfigHint
from pkgcore.restrictions.delegated import delegate
from pkgcore.restrictions import packages, values
from pkgcore.util.file import iter_read_bash
from pkgcore.ebuild.atom import (generate_collapsed_restriction)
from pkgcore.repository import multiplex, visibility
from pkgcore.util.lists import (stable_unique, unstable_unique)
from pkgcore.util.compatibility import any
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.config.errors import BaseException
from pkgcore.util.demandload import demandload
from pkgcore.ebuild import const
from pkgcore.ebuild.profiles import incremental_expansion
from pkgcore.util.parserestrict import parse_match
from pkgcore.util.currying import partial
from pkgcore.ebuild.misc import (collapsed_restrict_to_data,
    non_incremental_collapsed_restrict_to_data)

demandload(
    globals(),
    'errno '
    'pkgcore.util:osutils '
    )

class MissingFile(BaseException):
    def __init__(self, filename, setting):
        BaseException.__init__(self,
                               "setting %s points at %s, which doesn't exist."
                               % (setting, filename))
        self.file, self.setting = filename, setting

class Failure(BaseException):
    def __init__(self, text):
        BaseException.__init__(self, "domain failure: %s" % (text,))
        self.text = text


def package_keywords_splitter(val):
    v = val.split()
    return parse_match(v[0]), stable_unique(v[1:])


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
        'name': 'str',
        }
    for _thing in list(const.incrementals) + ['bashrc']:
        _types[_thing] = 'list'
    for _thing in [
        'package.mask', 'package.keywords', 'package.license', 'package.use',
        'package.unmask']:
        _types[_thing] = 'list'
        _types[_thing + '-dirs'] = 'list'
    for _thing in ['root', 'CHOST', 'CFLAGS', 'PATH', 'PORTAGE_TMPDIR',
                   'DISTCC_PATH', 'DISTCC_DIR', 'CCACHE_DIR']:
        _types[_thing] = 'str'

    # TODO this is missing defaults
    pkgcore_config_type = ConfigHint(
            _types, incrementals=const.incrementals, typename='domain',
            required=['repositories', 'profile', 'vdb', 'fetcher', 'name'],
            allow_unknowns=True)

    del _types, _thing

    def __init__(self, profile, repositories, vdb, name=None,
        root='/', incrementals=const.incrementals, **settings):
        # voodoo, unfortunately (so it goes)
        # break this up into chunks once it's stabilized (most of code
        # here has already, but still more to add)
        settings.setdefault('ACCEPT_LICENSE', const.ACCEPT_LICENSE)

        # map out sectionname -> config manager immediately.
        repositories_collapsed = [r.collapse() for r in repositories]
        repositories = [r.instantiate() for r in repositories_collapsed]
        vdb_collapsed = [r.collapse() for r in vdb]
        vdb = [r.instantiate() for r in vdb_collapsed]
        self.named_repos = dict(
            (collapsed.name, repo) for (collapsed, repo) in izip(
                repositories_collapsed, repositories))
        self.named_repos.update(
            (collapsed.name, repo) for (collapsed, repo) in izip(
                vdb_collapsed, vdb))
        self.named_repos.pop(None, None)

        pkg_maskers = set(profile.masks)
        for r in repositories:
            pkg_maskers.update(r.default_visibility_limiters)
        pkg_maskers = list(pkg_maskers)
        pkg_unmaskers, pkg_keywords, pkg_license = [], [], []
        pkg_use = []

        for key, val, action in (
            ("package.mask", pkg_maskers, parse_match),
            ("package.unmask", pkg_unmaskers, parse_match),
            ("package.keywords", pkg_keywords, package_keywords_splitter),
            ("package.license", pkg_license, package_keywords_splitter),
            ("package.use", pkg_use, package_keywords_splitter)):

            for fp in settings.pop(key, ()):
                try:
                    val.extend(action(x) for x in iter_read_bash(fp))
                except (IOError, OSError), e:
                    if e.errno == errno.ENOENT:
                        raise MissingFile(settings[key], key)
                    raise Failure("failed reading '%s': %s" % (fp, e))
                except ValueError, e:
                    raise Failure("failed reading '%s': %s" % (fp, e))
            for dirpath in settings.pop('%s-dirs' % (key,), ()):
                try:
                    files = osutils.listdir_files(dirpath)
                except (OSError, IOError), e:
                    raise Failure('failed listing %r: %s' % (dirpath, e))
                for fp in files:
                    if fp.startswith('.'):
                        continue
                    fp = osutils.join(dirpath, fp)
                    try:
                        val.extend(action(x) for x in iter_read_bash(fp))
                    except (IOError, OSError, ValueError), e:
                        raise Failure('failed reading %r: %r' % (fp, str(e)))

        self.name = name
        settings.setdefault("PKGCORE_DOMAIN", name)
        for x in incrementals:
            if isinstance(settings.get(x), basestring):
                settings[x] = set(settings[x].split())

        for x, v in profile.default_env.iteritems():
            if x in settings:
                if x in incrementals:
                    if isinstance(v, basestring):
                        v = set(v.split())
                    else:
                        v = set(v)
                    incremental_expansion(v, settings[x])
                    settings[x] = v
            else:
                if x in incrementals:
                    if isinstance(v, basestring):
                        v = set(v.split())
                    settings[x] = v
                else:
                    settings[x] = v

        # use is collapsed; now stack use_expand.
        use = settings.setdefault("USE", set())

        # hackish implementation; if test is on, flip on the flag
        if "test" in settings.get("FEATURES", []):
            use.add("test")

        for u in profile.use_expand:
            v = settings.get(u)
            if v is None:
                continue
            u2 = u.lower()+"_"
            use.update(u2 + x for x in settings[u].split())

        # visibility mask...
        # if ((package.mask or visibility) and not package.unmask)
        # or not (package.keywords or accept_keywords)

        vfilter = packages.AndRestriction(finalize=False,
            disable_inst_caching=False)
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
        for k, v in (("ACCEPT_KEYWORDS", default_keywords),
                     ("ACCEPT_LICENSE", master_license)):
            if k not in settings:
                raise Failure("No %s setting detected from profile, "
                              "or user config" % k)
            s = set()
            incremental_expansion(s, settings[k], "while expanding %s: " % k)
            v.extend(s)
            settings[k] = v


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

        # if it's made it this far...

        self.root = settings["ROOT"] = root
        self.settings = settings

        bashrc = list(profile.bashrc)

        if "bashrc" in self.settings:
            for data in self.settings['bashrc']:
                source = local_source(data)
                # this is currently local-only so a get_path check is ok
                # TODO make this more general
                if source.get_path() is None:
                    raise Failure(
                        'user-specified bashrc %r does not exist' % (data,))
                bashrc.append(source)

        # stack use stuff first, then profile.
        # could do an intersect up front to pull out the forced disabled
        # also, although that code would be fugly
        self.enabled_use = collapsed_restrict_to_data(
            ((packages.AlwaysTrue, self.use),
            (packages.AlwaysTrue, [self.arch])), pkg_use)
        self.forced_use = collapsed_restrict_to_data(
            profile.forced_use.iteritems(),
            ((packages.AlwaysTrue, [self.arch]),))
        self.disabled_use = collapsed_restrict_to_data(
            profile.masked_use.iteritems())

        self.settings["bashrc"] = bashrc
        self.repos = []
        self.vdb = []
        self.configured_named_repos = {}
        self.filtered_named_repos = {}

        rev_names = dict((repo, name) for name, repo in self.named_repos.iteritems())

        profile_repo = None
        if profile.virtuals:
            profile_repo = profile.make_virtuals_repo(multiplex.tree(*repositories))
            self.named_repos["profile virtuals"] = profile_repo
            self.filtered_named_repos["profile virtuals"] = profile_repo
            self.configured_named_repos["profile virtuals"] = profile_repo


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
                                pargs.append(ProtectedDict(settings))
                            elif x == "profile":
                                pargs.append(profile)
                            else:
                                pargs.append(getattr(self, x))
                    except AttributeError, ae:
                        raise Failure("failed configuring repo '%s': "
                                      "configurable missing: %s" % (repo, ae))
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
                    
        if profile_repo is not None:
            self.repos = [profile_repo] + self.repos

    def make_license_filter(self, master_license, pkg_licenses):
        data = collapsed_restrict_to_data(
            ((packages.AlwaysTrue, master_license),),
            pkg_licenses)
        return delegate(partial(self.apply_license_filter, data))

    def apply_license_filter(self, data, pkg, mode):
        # note we're not honoring mode; it's always match.
        # reason is that of not turning on use flags to get acceptible license
        # pairs.
        # maybe change this down the line?
        allowed_licenses = data.pull_data(pkg)
        for and_pair in pkg.license.dnf_solutions():
            for license in and_pair:
                if license not in allowed_licenses:
                    break
            else:
                # tiz fine.
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
            f = self.incremental_apply_keywords_filter
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

    def make_per_package_use(self, default_use, pkg_use):
        if not pkg_use:
            return default_use, ((), {})
        return collapsed_restrict_to_data(default_use, pkg_use)

    def get_package_use(self, pkg):
        disabled = self.disabled_use.pull_data(pkg)
        enabled = self.enabled_use.pull_data(pkg)
        immutable = self.forced_use.pull_data(pkg, False)
        if disabled:
            if enabled is self.enabled_use.defaults:
                enabled = set(enabled)
            if immutable is self.forced_use.defaults:
                immutable = set(immutable)
        elif immutable:
            if enabled is self.enabled_use.defaults:
                enabled = set(enabled)
        else:
            return immutable, enabled
        enabled.update(immutable)
        enabled.difference_update(disabled)
        immutable.update(disabled)

        return immutable, enabled
