# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo configuration domain
"""

# XXX doc this up better...

import os, operator
import pkgcore.config.domain
from itertools import chain, imap
from pkgcore.restrictions.delegated import delegate
from pkgcore.restrictions import packages, values, restriction
from pkgcore.util.file import iter_read_bash
from pkgcore.ebuild.atom import (atom, generate_collapsed_restriction)
from pkgcore.repository import multiplex, visibility
from pkgcore.restrictions.values import StrGlobMatch, ContainmentMatch
from pkgcore.util.lists import (stable_unique, unstable_unique,
    iflatten_instance)
from pkgcore.util.mappings import ProtectedDict
from pkgcore.interfaces.data_source import local_source
from pkgcore.config.errors import BaseException
from pkgcore.util.demandload import demandload
from pkgcore.ebuild.profiles import incremental_negations
from pkgcore.util.commandline import generate_restriction

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
    return generate_restriction(v[0]), stable_unique(v[1:])


# ow ow ow ow ow ow....
# this manages a *lot* of crap.  so... this is fun.
#
# note also, that this is rather ebuild centric. it shouldn't be, and
# should be redesigned to be a seperation of configuration
# instantiation manglers, and then the ebuild specific chunk (which is
# selected by config)
# ~harring


def make_data_dict(*iterables):
    """
    descriptive, no?
    
    Basically splits an iterable of restrict:data into
    level of specificity, repo, cat, pkg, atom (dict) for use
    in filters
    """

    repo = []    
    cat = []
    pkg = []
    atom_d = {}
    for iterable in iterables:
        for a, data in iterable:
            if not data:
                if not isinstance(a, (atom, packages.PackageRestriction,
                    restriction.AlwaysBool)):
                    raise ValueError("%r is not a AlwaysBool, "
                        "PackageRestriction, or atom: data %r" % (a, data))
                continue
            if isinstance(a, atom):
                atom_d.setdefault(a.key, []).append((a, data))
            elif isinstance(a, packages.PackageRestriction):
                if a.attr == "category":
                    cat.append((a, data))
                elif a.attr == "package":
                    pkg.append((a, data))
                else:
                    raise ValueError("%r doesn't operate on package/category: "
                        "data %r" % (a, data))
            elif isinstance(a, restriction.AlwaysBool):
                repo.append((a, data))
            else:
                raise ValueError("%r is not a AlwaysBool, PackageRestriction, "
                    "or atom: data %r" % (a, data))

    return [[repo, cat, pkg], 
        dict((k, tuple(v)) for k, v in atom_d.iteritems())]

def generic_collapse_data(specifics_tuple, pkg):
    for specific in specifics_tuple[0]:
        for restrict, data in specific:
            if restrict.match(pkg):
                yield data
    for atom, data in specifics_tuple[1].get(pkg.key, ()):
        if atom.match(pkg):
            yield data


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
        pkg_use = []

        for key, val, action in (
            ("package.mask", pkg_maskers, generate_restriction),
            ("package.unmask", pkg_unmaskers, generate_restriction),
            ("package.keywords", pkg_keywords, package_keywords_splitter),
            ("package.license", pkg_license, package_keywords_splitter),
            ("package.use", pkg_use, package_keywords_splitter)):

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

        use, license, default_keywords = [], [], []
        self.use = use
        self.immutable_use = ()
        self.package_use = {}
        master_license = []
        for k, v in (("USE", use),
                     ("ACCEPT_KEYWORDS", default_keywords),
                     ("ACCEPT_LICENSE", master_license)):
            if k not in settings:
                raise Failure("No %s setting detected from profile, "
                              "or user config" % k)
            v.extend(incremental_negations(k, settings[k]))
            settings[k] = v

        for u in profile.use_expand:
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

        vfilter.add_restriction(self.make_keywords_filter(
            arch, default_keywords, pkg_keywords))

        del default_keywords
        # we can finally close that fricking
        # "DISALLOW NON FOSS LICENSES" bug via this >:)
        if master_license:
            vfilter.add_restriction(self.make_license_filter(
                master_license, license))

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

        # finally, package.use
        self.use, self.package_use = self.make_per_package_use(
            self.use, pkg_use)
        self.profile_use_force = tuple(profile.use_force)
        self.profile_use_mask = tuple("-"+x for x in profile.use_mask)
        new_d = dict((k, tuple(v.iteritems()))
            for k,v in profile.package_use_force.iteritems())
        self.profile_package_use = ((), new_d)
        new_d = dict((k, tuple(v.iteritems()))
            for k,v in profile.package_use_mask.iteritems())
        self.profile_package_use_mask = ((), new_d)

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

    def make_license_filter(self, master_license, pkg_licenses):
        if not pkg_licenses:
            # simple case.
            return packages.PackageRestriction("license",
                values.ContainmentMatch(*master_license))

        # not so simple case.
        data = make_data_dict(pkg_licenses)
        # integrate any repo stackings now, stupid as they may be.
        repo = data[0].pop(0)
        repo = tuple(incremental_negations("license", 
            chain(master_license, (x[1] for x in repo))))
        # finalize it, and filter any unused specific blocks
        data[0] = tuple(filter(None, data[0]))
        data = tuple(data)
        return delegate(self.apply_license_filter, (repo, data))

    @staticmethod
    def apply_license_filter(data, pkg, mode):
        # note we're not using a restriction here; no point, this is faster.
        repo, data = data
        license = incremental_negations("license", chain(repo,
                iflatten_instance(generic_collapse_data(data, pkg))))
        if mode == "match":
            return operator.truth(license.intersection(pkg.license))
        return getattr(packages.PackageRestriction("license", 
            values.ContainmentMatch(*license)), mode)(pkg)

    def make_keywords_filter(self, arch, default_keys, pkg_keywords):
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
                else:
                    return r, v
            data = make_data_dict(f(*i) for i in pkg_keywords)
        else:
            data = make_data_dict(pkg_keywords)
        
        repo = data[0].pop(0)
        repo = tuple(incremental_negations("keywords",
            chain(default_keys, (x[1] for x in repo))))
        # finalize it, and filter any unused specific blocks
        data[0] = tuple(filter(None, data[0]))
        data = tuple(data)
        
        return delegate(self.apply_keywords_filter, (repo, data))
    
    @staticmethod
    def apply_keywords_filter(data, pkg, mode):
        # note we ignore mode; keywords aren't influenced by conditionals.
        # note also, we're not using a restriction here.  this is faster.
        repo, data = data
        allowed = incremental_negations("license", chain(repo,
                iflatten_instance(generic_collapse_data(data, pkg))))
        return operator.truth(allowed.intersection(pkg.keywords))

    def make_per_package_use(self, default_use, pkg_use):
        if not pkg_use:
            return default,use, ((), {})
        data = make_data_dict(pkg_use)
        repo = data[0].pop(0)
        repo = tuple(incremental_negations("use",
            chain(default_use, (x[1] for x in repo))))
        data[0] = tuple(filter(None, data[0]))
        data = tuple(data)
        return default_use, data

    def get_package_use(self, default_use, pkg):
        disabled = list(self.profile_use_mask)
        for data in generic_collapse_data(self.profile_package_use_mask, pkg):
            disabled += data
                
        enabled = set(default_use)
        for data in generic_collapse_data(self.package_use, pkg):
            incremental_negations("use", data, enabled)
        for data in generic_collapse_data(self.profile_package_use, pkg):
            incremental_negations("use", data, enabled)
        enabled.update(self.profile_use_force)
        enabled.difference_update(disabled)
        return disabled,enabled                
