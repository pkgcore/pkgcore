# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo configuration domain
"""

# XXX doc this up better...

import os
import pkgcore.config.domain
from pkgcore.restrictions.collapsed import DictBased
from pkgcore.restrictions import packages, values
from pkgcore.util.file import iter_read_bash
from pkgcore.ebuild.atom import (atom, generate_collapsed_restriction,
    get_key_from_package)
from pkgcore.repository import multiplex, visibility
from pkgcore.restrictions.values import StrGlobMatch, ContainmentMatch
from pkgcore.util.lists import stable_unique, unstable_unique
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.config.errors import BaseException
from pkgcore.util.demandload import demandload
from pkgcore.ebuild.profiles import incremental_list_negations
demandload(globals(), "warnings")

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
    return atom(v[0]), stable_unique(v[1:])


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
    def __init__(self, incrementals, root, profile, repositories, vdb,
                 name=None, **settings):
        # voodoo, unfortunately (so it goes)
        # break this up into chunks once it's stabilized (most of code
        # here has already, but still more to add)
        pkg_maskers = list(profile.maskers)
        pkg_unmaskers, pkg_keywords, pkg_license = [], [], []

        for key, val, action in (
            ("package.mask", pkg_maskers, atom),
            ("package.unmask", pkg_unmaskers, atom),
            ("package.keywords", pkg_keywords, package_keywords_splitter),
            ("package.license", pkg_license, package_keywords_splitter)):

            if key in settings:
                for fp in settings[key]:
                    # unecessary stating.
                    if os.path.exists(fp):
                        try:
                            val.extend(action(x) for x in iter_read_bash(fp))
                        except (IOError, OSError, ValueError), e:
                            raise Failure(
                                "failed reading '%s': %s" % (fp, str(e)))
                    else:
                        raise MissingFile(settings[key], key)
                del settings[key]


        self.name = name
        settings.setdefault("PKGCORE_DOMAIN", name)
        inc_d = set(incrementals)
        inc_d.update(profile.use_expand)
        for x in profile.conf:
            if x in settings:
                if x in inc_d:
                    # strings overwrite, lists append.
                    if isinstance(settings[x], (list, tuple)):
                        # profile prefixes
                        settings[x] = profile.conf[x] + settings[x]
            else:
                settings[x] = profile.conf[x]
        del inc_d

        # visibility mask...
        # if ((package.mask or visibility) and not package.unmask)
        # or not (package.keywords or accept_keywords)

        vfilter = packages.AndRestriction(finalize=False, inst_caching=False)
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

        use, license, default_keywords = [], [], []
        self.use = use
        master_license = []
        for k, v in (("USE", use),
                     ("ACCEPT_KEYWORDS", default_keywords),
                     ("ACCEPT_LICENSE", master_license)):
            if k not in settings:
                raise Failure("No %s setting detected from profile, "
                              "or user config" % k)
            v.extend(incremental_list_negations(k, settings[k]))
            settings[k] = v

        for u in profile.use_expand:
            if k not in settings:
                continue
            u2 = u.lower()+"_"
            if u in settings:
                use.extend(u2 + x for x in settings[u].split())

        if "ARCH" not in settings:
            raise Failure(
                "No ARCH setting detected from profile, or user config")

        arch = settings["ARCH"]

        # ~amd64 -> [amd64, ~amd64]
        for x in default_keywords[:]:
            if x.startswith("~"):
                default_keywords.append(x.lstrip("~"))
        default_keywords = unstable_unique(default_keywords + [arch])

        keywords_filter = self.generate_keywords_filter(
            arch, default_keywords, pkg_keywords,
            already_unstable=("~%s" % arch.lstrip("~") in default_keywords))
        vfilter.add_restriction(keywords_filter)
        del keywords_filter
        # we can finally close that fricking
        # "DISALLOW NON FOSS LICENSES" bug via this >:)
        if master_license:
            if license:
                r = packages.OrRestriction(negate=True)
                r.add_restriction(packages.PackageRestriction(
                        "license", ContainmentMatch(*master_license)))
                r.add_restriction(DictBased(license, get_key_from_package))
                vfilter.add_restriction(r)
            else:
                vfilter.add_restriction(packages.PackageRestriction(
                        "license", ContainmentMatch(*master_license)))
        elif license:
            vfilter.add_restriction(DictBased(license, get_key_from_package))

        del master_license, license

        # if it's made it this far...

        settings["ROOT"] = root
        # this should be handled via another means
        if "default" in settings:
            del settings["default"]
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

        self.settings["bashrc"] = bashrc
        self.repos = []
        self.vdb = []
        profile_repo = None
        if profile.virtuals:
            profile_repo = profile.virtuals(multiplex.tree(*repositories))
        for l, repos in ((self.repos, repositories), (self.vdb, vdb)):
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
                    l.append(repo.configure(*pargs))
                else:
                    l.append(repo)
                # do this once at top level instead.

        self.repos = [visibility.filterTree(t, vfilter, True)
                      for t in self.repos]
        if profile_repo is not None:
            self.repos = [profile_repo] + self.repos


    def generate_keywords_filter(self, arch, default_keys, pkg_keywords,
                                 already_unstable=False):
        """Generates a restrict that matches iff the keywords are allowed."""
        if not pkg_keywords:
            return packages.PackageRestriction(
                "keywords", values.ContainmentMatch(*default_keys))

        keywords_filter = {}

        # save on instantiation caching/creation costs.
        if already_unstable:
            unstable_restrict = ContainmentMatch(*default_keys)
        else:
            unstable_restrict = ContainmentMatch("~%s" % arch.lstrip("~"),
                                                 *default_keys)
        unstable_pkg_restrict = packages.PackageRestriction("keywords",
                                                            unstable_restrict)
        default_restrict = ContainmentMatch(*default_keys)
        default_keys = set(default_keys)

        second_level_restricts = {}
        for pkgatom, vals in pkg_keywords:
            if not vals:
                # if we already are unstable, no point in adding this exemption
                if already_unstable:
                    continue
                r = unstable_pkg_restrict
            else:
                per, glob, negated = [], [], []
                for x in vals:
                    s = x.lstrip("-")
                    negate = x.startswith("-")
                    if "~*" == s:
                        if negate:
                            raise Failure("can't negate -~* keywords")
                        glob.append(StrGlobMatch("~"))
                    elif "*" == s:
                        if negate:
                            warnings.warn("-* detected in keywords stack; "
                                          "-* isn't a valid target, ignoring")
                            continue
                        # stable only, exempt unstable
                        glob.append(StrGlobMatch("~", negate=True))
                    elif negate:
                        negated.append(s)
                    else:
                        per.append(s)
                r = values.OrRestriction(inst_caching=False)
                if per:
                    r.add_restriction(ContainmentMatch(*per))
                if glob:
                    r.add_restriction(*glob)
                if negated:
                    if r.restrictions:
                        r.add_restriction(values.ContainmentMatch(
                                *default_keys.difference(negated)))
                    else:
                        # strictly a limiter of defaults.  yay.
                        r = values.ContainmentMatch(
                            *default_keys.difference(negated))
                else:
                    r.add_restriction(default_restrict)
                r = packages.PackageRestriction("keywords", r)
            second_level_restricts.setdefault(pkgatom.key, []).append(pkgatom)
            keywords_filter[pkgatom] = r

        second_level_restricts = dict(
            (k, tuple(unstable_unique(v)))
            for k, v in second_level_restricts.iteritems())

        keywords_filter["__DEFAULT__"] = packages.PackageRestriction(
            "keywords", default_restrict)
        def redirecting_splitter(collapsed_inst, pkg):
            key = get_key_from_package(collapsed_inst, pkg)
            for pkgatom in second_level_restricts.get(key, []):
                if pkgatom.match(pkg):
                    return pkgatom
            return "__DEFAULT__"
            return key

        return DictBased(keywords_filter.iteritems(), redirecting_splitter)
