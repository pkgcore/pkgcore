# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
package class for buildable ebuilds
"""

import os, operator
from pkgcore.package import metadata, errors

WeakValCache = metadata.WeakValCache

from pkgcore.ebuild import conditionals
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.digest import parse_digest
from pkgcore.util.mappings import IndeterminantDict
from pkgcore.util.currying import post_curry, alias_class_method, pre_curry
from pkgcore.util.lists import ChainedLists
from pkgcore.restrictions.packages import AndRestriction
from pkgcore.restrictions import boolean
from pkgcore.chksum.errors import MissingChksum
from pkgcore.fetch.errors import UnknownMirror
from pkgcore.fetch import fetchable, mirror
from pkgcore.ebuild import const, processor
from pkgcore.util.demandload import demandload
demandload(globals(), "pkgcore.util.xml:etree")
demandload(globals(), "errno")


# utility func.
def create_fetchable_from_uri(pkg, chksums, mirrors, default_mirrors,
                              common_files, uri):

    filename = os.path.basename(uri)

    preexisting = filename in common_files

    if not preexisting:
        if filename not in chksums:
            raise MissingChksum(filename)

    if filename == uri:
        new_uri = []
    else:
        if not preexisting:
            new_uri = []
            if "primaryuri" in pkg.restrict:
                new_uri.append([uri])

            if default_mirrors is not None and "mirror" not in pkg.restrict:
                new_uri.append(mirror(filename, default_mirrors,
                                      "conf_default_mirrors"))
        else:
            new_uri = common_files[filename].uri

        if uri.startswith("mirror://"):
            # mirror:// is 9 chars.
            tier, remaining_uri = uri[9:].split("/", 1)
            if tier not in mirrors:
                raise UnknownMirror(tier, remaining_uri)
            new_uri.append(mirror(remaining_uri, mirrors[tier], tier))
            # XXX replace this with an iterable instead
        else:
            if not new_uri or new_uri[0] != [uri]:
                new_uri.append([uri])

    # force usage of a ChainedLists, why? because folks may specify
    # multiple uri's resulting in the same file. we basically use
    # ChainedList's _list as a mutable space we directly modify.
    if not preexisting:
        common_files[filename] = fetchable(
            filename, ChainedLists(*new_uri), chksums[filename])
    return common_files[filename]

def generate_depset(s, c, *keys, **kwds):
    if kwds.pop("non_package_type", False):
        kwds["operators"] = {"||":boolean.OrRestriction,
                             "":boolean.AndRestriction}
    try:
        return conditionals.DepSet(" ".join([s.data.get(x.upper(), "")
                                             for x in keys]), c, **kwds)
    except conditionals.ParseError, p:
        raise errors.MetadataException(s, str(keys), str(p))

def generate_providers(self):
    rdep = AndRestriction(self.versioned_atom, finalize=True)
    func = pre_curry(virtual_ebuild, self._parent, self,
                      {"rdepends":rdep, "slot":self.version})
    # re-enable license at some point.
    #, "license":self.license})

    try:
        return conditionals.DepSet(
            self.data.get("PROVIDE", ""), virtual_ebuild, element_func=func,
            operators={"||":boolean.OrRestriction,"":boolean.AndRestriction})

    except conditionals.ParseError, p:
        raise errors.MetadataException(self, "provide", str(p))

def generate_fetchables(self):
    chksums = parse_digest(os.path.join(
        os.path.dirname(self._parent._get_ebuild_path(self)), "files",
        "digest-%s-%s" % (self.package, self.fullver)))
    try:
        mirrors = self._parent.mirrors
    except AttributeError:
        mirrors = {}
    try:
        default_mirrors = self._parent.default_mirrors
    except AttributeError:
        default_mirrors = None
    try:
        return conditionals.DepSet(
            self.data["SRC_URI"], fetchable, operators={},
            element_func=pre_curry(create_fetchable_from_uri, self, chksums,
                                   mirrors, default_mirrors, {}))
    except conditionals.ParseError, p:
        raise errors.MetadataException(self, "src_uri", str(p))

def generate_eapi(self):
    try:
        val = int(self.data.get("EAPI", 0))
    except ValueError:
        if self.data["EAPI"] == '':
            val = 0
        else:
            val = const.unknown_eapi
    except KeyError:
        val = 0
    return val

metadata_xml_attr_map = {"maintainers":0, "herds":1, "longdescription":2}

def pull_metadata_xml(self, attr):
    o = getattr(self._pkg_metadata_shared, attr)
    if o == -1:
        try:
            tree = etree.parse(self._parent._get_metadata_xml_path(self))
            maintainers = []
            for x in tree.findall("maintainer"):
                name = email = None
                for e in x:
                    if e.tag == "name":
                        name = e.text
                    elif e.tag == "email":
                        email = e.text
                if name is not None:
                    if email is not None:
                        maintainers.append("%s <%s>" % (name, email))
                    else:
                        maintainers.append(name)
                elif email is not None:
                    maintainers.append(email)

            self._pkg_metadata_shared.maintainers = tuple(maintainers)
            self._pkg_metadata_shared.herds = tuple(str(x.text)
                for x in tree.findall("herd"))

            # Could be unicode!
            longdesc = tree.findtext("longdescription")
            if longdesc:
                longdesc = ' '.join(longdesc.strip().split())
            self._pkg_metadata_shared.longdescription = longdesc

        except IOError, i:
            if i.errno != errno.ENOENT:
                raise
            self._pkg_metadata_shared.herds = ()
            self._pkg_metadata_shared.maintainers = ()
            self._pkg_metadata_shared.longdescription = None
        o = getattr(self._pkg_metadata_shared, attr)
    return o

def rewrite_restrict(restrict):
    l = set()
    for x in restrict:
        if x.startswith("no"):
            l.add(x[2:])
        else:
            l.add(x)
    return tuple(l)

class package(metadata.package):

    """
    ebuild package

    @cvar tracked_attributes: sequence of attributes that are required to exist
        in the built version of ebuild-src
    @cvar _config_wrappables: mapping of attribute to callable for
        re-evaluating attributes dependant on configuration
    """

    immutable = False
    allow_regen = True
    tracked_attributes = [
        "PF", "depends", "rdepends", "post_rdepends", "provides", "license",
        "slot", "keywords", "eapi", "restrict", "eapi", "description", "iuse"]

    _config_wrappables = dict((x, alias_class_method("evaluate_depset"))
        for x in ["depends", "rdepends", "post_rdepends", "fetchables",
                  "license", "src_uri", "license", "provides"])

    def __init__(self, parent, cpv):
        metadata.package.__init__(self, parent, cpv)

    _get_attr = dict(metadata.package._get_attr)
    _get_attr["provides"] = generate_providers
    _get_attr["depends"] = post_curry(generate_depset, atom, "depend")
    _get_attr["rdepends"] = post_curry(generate_depset, atom, "rdepend")
    _get_attr["post_rdepends"] = post_curry(generate_depset, atom, "pdepend")
    _get_attr["license"] = post_curry(generate_depset, str, "license",
                                      non_package_type=True)
    _get_attr["slot"] = lambda s: s.data.get("SLOT", "0").strip()
    _get_attr["fetchables"] = generate_fetchables
    _get_attr["description"] = lambda s:s.data.get("DESCRIPTION", "").strip()
    _get_attr["keywords"] = lambda s:tuple(map(intern,
        s.data.get("KEYWORDS", "").split()))
    _get_attr["restrict"] = lambda s:rewrite_restrict(
            s.data.get("RESTRICT", "").split())
    _get_attr["eapi"] = generate_eapi
    _get_attr["iuse"] = lambda s:tuple(map(intern,
        s.data.get("IUSE", "").split()))
    _get_attr["homepage"] = lambda s:s.data.get("HOMEPAGE", "").strip()

    __slots__ = tuple(_get_attr.keys() + ["_pkg_metadata_shared"])

    @property
    def P(self):
        return "%s-%s" % (self.package, self.version)
    
    @property
    def PF(self):
        return "%s-%s" % (self.package, self.fullver)

    @property
    def PN(self):
        return self.package

    @property
    def PR(self):
        r = self.revision
        if r is not Nne:
            return r
        return 0

    @property
    def ebuild(self):
        return self._parent.get_ebuild_src(self)
    
    @property
    def maintainers(self):
        return pull_metadata_xml(self, "maintainers")
    
    @property
    def herds(self):
        return pull_metadata_xml(self, "herds")
    
    @property
    def longdescription(self):
        return pull_metadata_xml(self, "longdescription")
    
    @property
    def _mtime_(self):
        return self._parent._get_ebuild_mtime(self)

    def _fetch_metadata(self):
        d = self._parent._get_metadata(self)
        return d

    def __str__(self):
        return "ebuild src: %s" % self.cpvstr

    def __repr__(self):
        return "<%s cpv=%r @%#8x>" % (self.__class__, self.cpvstr, id(self))


class package_factory(metadata.factory):
    child_class = package

    def __init__(self, parent, cachedb, eclass_cache, mirrors, default_mirrors,
                 *args, **kwargs):
        super(package_factory, self).__init__(parent, *args, **kwargs)
        self._cache = cachedb
        self._ecache = eclass_cache
        self.mirrors = mirrors
        self.default_mirrors = default_mirrors
        self._weak_pkglevel_cache = WeakValCache()

    def get_ebuild_src(self, pkg):
        return self._parent_repo._get_ebuild_src(pkg)

    def _get_metadata_xml_path(self, pkg):
        return self._parent_repo._get_metadata_xml_path(pkg)

    def _get_metadata(self, pkg):
        for cache in self._cache:
            if cache is not None:
                try:
                    data = cache[pkg.cpvstr]
                except KeyError:
                    continue
#                if not self.allow_regen:
#                    return data
                if long(data.get("_mtime_", -1)) != pkg._mtime_ or \
                    self._invalidated_eclasses(data, pkg):
                    continue
                return data

        # no cache entries, regen
        return self._update_metadata(pkg)

    def _invalidated_eclasses(self, data, pkg):
        return (data.get("_eclasses_") is not None and not
            self._ecache.is_eclass_data_valid(data["_eclasses_"]))

    def _get_ebuild_path(self, pkg):
        return self._parent_repo._get_ebuild_path(pkg)

    def _get_ebuild_mtime(self, pkg):
        return long(os.stat(self._get_ebuild_path(pkg)).st_mtime)

    def _update_metadata(self, pkg):
        ebp = processor.request_ebuild_processor()
        try:
            mydata = ebp.get_keys(pkg, self._ecache)
        finally:
            processor.release_ebuild_processor(ebp)

        mydata["_mtime_"] = pkg._mtime_
        if mydata.get("INHERITED", False):
            mydata["_eclasses_"] = self._ecache.get_eclass_data(
                mydata["INHERITED"].split())
            del mydata["INHERITED"]
        else:
            mydata["_eclasses_"] = {}

        if self._cache is not None:
            self._cache[0][pkg.cpvstr] = mydata

        return mydata

    def new_package(self, cpv):
        inst = self._cached_instances.get(cpv, None)
        if inst is None:
            inst = self._cached_instances[cpv] = self.child_class(
                self, cpv)
            o = self._weak_pkglevel_cache.get(inst.key, None)
            if o is None:
                o = SharedMetadataXml()
                self._weak_pkglevel_cache[inst.key] = o
            object.__setattr__(inst, "_pkg_metadata_shared", o)
        return inst


class SharedMetadataXml(object):
    """
    metadata.xml parsed reseults
    
    attributes are set to -1 if unloaded, None if no entry, or the value
    if loaded
    
    """
    
    __slots__ = ("__weakref__", "maintainers", "herds", "longdescription")
    
    
    def __init__(self):
        self.maintainers = -1
        self.herds = -1
        self.longdescription = -1 
    

generate_new_factory = package_factory


class virtual_ebuild(metadata.package):

    """
    PROVIDES generated fake packages
    """

    package_is_real = False
    built = True

    __slots__ = ("__dict__")

    def __init__(self, parent_repository, pkg, data, cpv):
        """
        @param cpv: cpv for the new pkg
        @param parent_repository: actual repository that this pkg should
            claim it belongs to
        @param pkg: parent pkg that is generating this pkg
        @param data: mapping of data to push to use in __getattr__ access
        """
        sfunc = object.__setattr__
        sfunc(self, "data", IndeterminantDict(lambda *a: str(), data))
        sfunc(self, "_orig_data", data)
        sfunc(self, "actual_pkg", pkg)
        # ick.
        state = set(self.__dict__)
        # hack. :)
        metadata.package.__init__(self, parent_repository, cpv)
        if not self.version:
            for x in self.__dict__.keys():
                if x not in state:
                    del self.__dict__[x]
            metadata.package.__init__(self, parent_repository,
                cpv+"-"+pkg.fullver)
            assert self.version

    def __getattr__(self, attr):
        if attr in self._orig_data:
            return self._orig_data[attr]
        return metadata.package.__getattr__(self, attr)

    _get_attr = package._get_attr.copy()
