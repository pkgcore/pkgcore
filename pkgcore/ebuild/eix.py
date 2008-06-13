from snakeoil.currying import post_curry
from pkgcore.package.base import base as ebuild_base
from pkgcore.ebuild.eix_utils import (number, string, vector, hash,
    hashed_words, hash_attr, hashed_word_attr, version_part, bitset)

supported = (26,)

class Repo(object):
    __slots__ = ('overlays', 'provides', 'licenses', 'keywords', 'useflags',
                 'slots', 'categories')
    def __init__(self, overlays, provides, licenses, keywords, useflags,
                 slots, categories):
        self.overlays = overlays
        self.provides = provides
        self.licenses = licenses
        self.keywords = keywords
        self.useflags = useflags
        self.slots = slots
        self.categories = categories

class Overlay(object):
    __slots__ = ('path', 'name')
    def __init__(self, path, name=None):
        self.path = path
        if not name:
            name = path
        self.name = name

    def __str__(self):
        if self.name != self.path:
            path = " @ %s" % self.path
        else:
            path = ""
        return "%s%s" % (self.name, path)

    @classmethod
    def instantiate(cls, f):
        """Instantiate an Overlay from a file obj"""
        path = string(f)
        name = string(f)
        return cls(path, name)


class Category(object):
    __slots__ = ('name', 'packages')
    def __init__(self, name, packages):
        self.name = name
        self.packages = packages

    @classmethod
    def instantiate(cls, f, repo):
        """Instantiate a Category from a file obj"""
        name = string(f)
        packages = vector(f, post_curry(Package.instantiate, repo))
        return cls(name, packages)



class EixVersion(object):
    __slots__ = ("_bitset", "_keywords", "suffix", "_slot", "_overlay",
                 "_use", "_package")
    def __init__(self, bitset, keywords, suffix, slot, overlay, use, package):
        self._bitset = bitset
        self._keywords = keywords
        self.suffix = suffix
        self._slot = slot
        self._overlay = overlay
        self._use = use
        self._package = package

    @classmethod
    def instantiate(cls, f, package):
        """Instantiate an EixVersion from a file obj"""
        b = bitset(ord(f.read(1)))
        keywords = hashed_words(f)
        suffix = ''.join(vector(f, version_part))
        slot = number(f)
        repo = number(f)
        use = hashed_words(f)
        return cls(b, keywords, suffix, slot, repo, use, package)


class Package(object):

    license = property(hash_attr("license"))
    provides = property(hash_attr("provides"))
    use = property(hashed_word_attr("use"))

    def __init__(self, name, description, provides, homepage, license, use,
                 versions, repo):
        self.name = name
        self.description = description
        self._provides = provides
        self.homepage = homepage
        self._license = license
        self._use = use
        self.versions = versions
        self._repo = repo

    @classmethod
    def instantiate(cls, f, repo):
        """Instantiate a Package from a file obj"""
        offset = number(f) # Use for seekahead?
        name = string(f)
        description = string(f)
        provides = number(f)
        homepage = string(f)
        license = number(f)
        use = hashed_words(f)
        p = cls(name, description, provides, homepage, license, use, (), repo)
        versions = vector(f, post_curry(EixVersion.instantiate, p))
        p._version = versions
        return p

def parse_header(f):
    version = number(f)
    if version not in supported:
        raise ValueError("Unsupported version %d" % version)
    cat_num = number(f)
    overlays = vector(f, Overlay.instantiate)
    provides = hash(f)
    licenses = hash(f)
    keywords = hash(f)
    useflags = hash(f)
    slots = hash(f)
    repo = Repo(overlays, provides, licenses, keywords, useflags, slots, ())
    repo.categories = tuple(Category.instantiate(f, repo) for x in xrange(cat_num))
    return repo
