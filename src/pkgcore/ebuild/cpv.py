"""gentoo ebuild specific base package class"""

from collections import UserString

from snakeoil.compatibility import cmp
from snakeoil.demandload import demand_compile_regexp

from ..package import base
from . import atom
from .errors import InvalidCPV

demand_compile_regexp(
    'suffix_regexp', '^(alpha|beta|rc|pre|p)(\\d*)$')

suffix_value = {"pre": -2, "p": 1, "alpha": -4, "beta": -3, "rc": -1}

# while the package section looks fugly, there is a reason for it-
# to prevent version chunks from showing up in the package

demand_compile_regexp(
    'isvalid_version_re',
    r"^(?:\d+)(?:\.\d+)*[a-zA-Z]?(?:_(p(?:re)?|beta|alpha|rc)\d*)*$")

demand_compile_regexp(
    'isvalid_cat_re', r"^(?:[a-zA-Z0-9][-a-zA-Z0-9+._]*(?:/(?!$))?)+$")

# empty string is fine, means a -- was encounter.
demand_compile_regexp(
    '_pkg_re', r"^[a-zA-Z0-9+_]+$")


def isvalid_pkg_name(chunks):
    if not chunks[0] or chunks[0][0] == '+':
        # this means a leading -; additionally, '+asdf' is disallowed
        return False
    mf = _pkg_re.match
    if not all(mf(s) for s in chunks[:-1]):
        return False
    if chunks[-1]:
        return mf(chunks[-1]) and not isvalid_version_re.match(chunks[-1])
    return True

def isvalid_rev(s):
    return s and s[0] == 'r' and s[1:].isdigit()


class Revision(UserString):
    """Internal revision class storing revisions as strings and comparing as integers."""

    # parent __hash__() isn't inherited when __eq__() is defined in the child class
    # https://docs.python.org/3/reference/datamodel.html#object.__hash__
    __hash__ = UserString.__hash__

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            self._revint = int(self.data)
        else:
            self._revint = 0

    def __str__(self):
        if not self.data:
            return '0'
        else:
            return self.data

    def __eq__(self, other):
        if isinstance(other, Revision):
            return self._revint == other._revint
        elif isinstance(other, int):
            return self._revint == other
        elif other is None:
            return self._revint == 0
        return self.data == other

    def __lt__(self, other):
        if isinstance(other, Revision):
            return self._revint < other._revint
        elif isinstance(other, int):
            return self._revint < other
        elif other is None:
            return self._revint < 0
        return self.data < other

    def __le__(self, other):
        if isinstance(other, Revision):
            return self._revint <= other._revint
        elif isinstance(other, int):
            return self._revint <= other
        elif other is None:
            return self._revint <= 0
        return self.data <= other

    def __gt__(self, other):
        if isinstance(other, Revision):
            return self._revint > other._revint
        elif isinstance(other, int):
            return self._revint > other
        elif other is None:
            return self._revint > 0
        return self.data > other

    def __ge__(self, other):
        if isinstance(other, Revision):
            return self._revint >= other._revint
        elif isinstance(other, int):
            return self._revint >= other
        elif other is None:
            return self._revint >= 0
        return self.data >= other


def ver_cmp(ver1, rev1, ver2, rev2):
    # If the versions are the same, comparing revisions will suffice.
    if ver1 == ver2:
        # revisions are equal if 0 or None (versionless cpv)
        if not rev1 and not rev2:
            return 0
        return cmp(rev1, rev2)

    # Split up the versions into dotted strings and lists of suffixes.
    parts1 = ver1.split("_")
    parts2 = ver2.split("_")

    # If the dotted strings are equal, we can skip doing a detailed comparison.
    if parts1[0] != parts2[0]:

        # First split up the dotted strings into their components.
        ver_parts1 = parts1[0].split(".")
        ver_parts2 = parts2[0].split(".")

        # Pull out any letter suffix on the final components and keep
        # them for later.
        letters = []
        for ver_parts in (ver_parts1, ver_parts2):
            if ver_parts[-1][-1].isalpha():
                letters.append(ord(ver_parts[-1][-1]))
                ver_parts[-1] = ver_parts[-1][:-1]
            else:
                # Using -1 simplifies comparisons later
                letters.append(-1)

        # OPT: Pull length calculation out of the loop
        ver_parts1_len = len(ver_parts1)
        ver_parts2_len = len(ver_parts2)

        # Iterate through the components
        for v1, v2 in zip(ver_parts1, ver_parts2):

            # If the string components are equal, the numerical
            # components will be equal too.
            if v1 == v2:
                continue

            # If one of the components begins with a "0" then they
            # are compared as floats so that 1.1 > 1.02; else ints.
            if v1[0] != "0" and v2[0] != "0":
                v1 = int(v1)
                v2 = int(v2)
            else:
                # handle the 0.060 == 0.060 case.
                v1 = v1.rstrip("0")
                v2 = v2.rstrip("0")

            # If they are not equal, the higher value wins.
            c = cmp(v1, v2)
            if c:
                return c

        if ver_parts1_len > ver_parts2_len:
            return 1
        elif ver_parts2_len > ver_parts1_len:
            return -1

        # The dotted components were equal. Let's compare any single
        # letter suffixes.
        if letters[0] != letters[1]:
            return cmp(letters[0], letters[1])

    # The dotted components were equal, so remove them from our lists
    # leaving only suffixes.
    del parts1[0]
    del parts2[0]

    # OPT: Pull length calculation out of the loop
    parts1_len = len(parts1)
    parts2_len = len(parts2)

    # Iterate through the suffixes
    for x in range(max(parts1_len, parts2_len)):

        # If we're at the end of one of our lists, we need to use
        # the next suffix from the other list to decide who wins.
        if x == parts1_len:
            match = suffix_regexp.match(parts2[x])
            val = suffix_value[match.group(1)]
            if val:
                return cmp(0, val)
            return cmp(0, int("0"+match.group(2)))
        if x == parts2_len:
            match = suffix_regexp.match(parts1[x])
            val = suffix_value[match.group(1)]
            if val:
                return cmp(val, 0)
            return cmp(int("0"+match.group(2)), 0)

        # If the string values are equal, no need to parse them.
        # Continue on to the next.
        if parts1[x] == parts2[x]:
            continue

        # Match against our regular expression to make a split between
        # "beta" and "1" in "beta1"
        match1 = suffix_regexp.match(parts1[x])
        match2 = suffix_regexp.match(parts2[x])

        # If our int'ified suffix names are different, use that as the basis
        # for comparison.
        c = cmp(suffix_value[match1.group(1)], suffix_value[match2.group(1)])
        if c:
            return c

        # Otherwise use the digit as the basis for comparison.
        c = cmp(int("0"+match1.group(2)), int("0"+match2.group(2)))
        if c:
            return c

    # Our versions had different strings but ended up being equal.
    # The revision holds the final difference.
    return cmp(rev1, rev2)


class CPV(base.base):
    """base ebuild package class

    :ivar category: str category
    :ivar package: str package
    :ivar key: strkey (cat/pkg)
    :ivar version: str version
    :ivar revision: str revision
    :ivar versioned_atom: atom matching this exact version
    :ivar unversioned_atom: atom matching all versions of this package
    """

    __slots__ = ("cpvstr", "key", "category", "package", "version", "revision", "fullver")

    def __init__(self, *args, versioned=None):
        """
        Can be called with one string or with three string args.

        If called with one arg that is the cpv string. (See :obj:`parser`
        for allowed syntax).

        If called with three args they are the category, package and
        version components of the cpv string respectively.
        """
        for x in args:
            if not isinstance(x, str):
                raise TypeError(f"all args must be strings, got {args!r}")

        l = len(args)
        if l == 1:
            cpvstr = args[0]
            if versioned is None:
                raise TypeError(
                    f"single argument invocation requires versioned kwarg; {cpvstr!r}")
        elif l == 2:
            cpvstr = f"{args[0]}/{args[1]}"
            versioned = False
        elif l == 3:
            cpvstr = f"{args[0]}/{args[1]}-{args[2]}"
            versioned = True
        else:
            raise TypeError(
                f"CPV takes 1 arg (cpvstr), 2 (cat, pkg), or 3 (cat, pkg, ver): got {args!r}")

        try:
            category, pkgver = cpvstr.rsplit("/", 1)
        except ValueError:
            # occurs if the rsplit yields only one item
            raise InvalidCPV(cpvstr, 'no package or version components')
        if not isvalid_cat_re.match(category):
            raise InvalidCPV(cpvstr, 'invalid category name')
        sf = object.__setattr__
        sf(self, 'category', category)
        sf(self, 'cpvstr', cpvstr)
        pkg_chunks = pkgver.split("-")
        lpkg_chunks = len(pkg_chunks)
        if versioned:
            if lpkg_chunks == 1:
                raise InvalidCPV(cpvstr, 'missing package version')
            if isvalid_rev(pkg_chunks[-1]):
                if lpkg_chunks < 3:
                    # needs at least ('pkg', 'ver', 'rev')
                    raise InvalidCPV(
                        cpvstr, 'missing package name, version, and/or revision')
                rev = Revision(pkg_chunks.pop(-1)[1:])
                if rev == 0:
                    # reset stored cpvstr to drop -r0+
                    sf(self, 'cpvstr', f"{category}/{'-'.join(pkg_chunks)}")
                elif rev[0] == '0':
                    # reset stored cpvstr to drop leading zeroes from revision
                    sf(self, 'cpvstr', f"{category}/{'-'.join(pkg_chunks)}-r{int(rev)}")
                sf(self, 'revision', rev)
            else:
                sf(self, 'revision', Revision(''))

            if not isvalid_version_re.match(pkg_chunks[-1]):
                raise InvalidCPV(cpvstr, f"invalid version '{pkg_chunks[-1]}'")
            sf(self, 'version', pkg_chunks.pop(-1))
            if self.revision:
                sf(self, 'fullver', f"{self.version}-r{self.revision}")
            else:
                sf(self, 'fullver', self.version)

            if not isvalid_pkg_name(pkg_chunks):
                raise InvalidCPV(cpvstr, 'invalid package name')
            sf(self, 'package', '-'.join(pkg_chunks))
            sf(self, 'key', f"{category}/{self.package}")
        else:
            if not isvalid_pkg_name(pkg_chunks):
                raise InvalidCPV(cpvstr, 'invalid package name')
            sf(self, 'revision', None)
            sf(self, 'fullver', None)
            sf(self, 'version', None)
            sf(self, 'key', cpvstr)
            sf(self, 'package', '-'.join(pkg_chunks))

    def __hash__(self):
        return hash(self.cpvstr)

    def __repr__(self):
        return '<%s cpvstr=%s @%#8x>' % (
             self.__class__.__name__, getattr(self, 'cpvstr', None), id(self))

    def __str__(self):
        return getattr(self, 'cpvstr', 'None')

    def __eq__(self, other):
        try:
            if self.cpvstr == other.cpvstr:
                return True
            if self.category == other.category and self.package == other.package:
                return ver_cmp(self.version, self.revision, other.version, other.revision) == 0
        except AttributeError:
            pass
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        try:
            if self.category == other.category:
                if self.package == other.package:
                    return ver_cmp(self.version, self.revision, other.version, other.revision) < 0
                return self.package < other.package
            return self.category < other.category
        except AttributeError:
            raise TypeError(
                "'<' not supported between instances of "
                f"{self.__class__.__name__!r} and {other.__class__.__name__!r}"
            )

    def __le__(self, other):
        try:
            if self.category == other.category:
                if self.package == other.package:
                    return ver_cmp(self.version, self.revision, other.version, other.revision) <= 0
                return self.package < other.package
            return self.category < other.category
        except AttributeError:
            raise TypeError(
                "'<=' not supported between instances of "
                f"{self.__class__.__name__!r} and {other.__class__.__name__!r}"
            )

    def __gt__(self, other):
        try:
            if self.category == other.category:
                if self.package == other.package:
                    return ver_cmp(self.version, self.revision, other.version, other.revision) > 0
                return self.package > other.package
            return self.category > other.category
        except AttributeError:
            raise TypeError(
                "'>' not supported between instances of "
                f"{self.__class__.__name__!r} and {other.__class__.__name__!r}"
            )

    def __ge__(self, other):
        try:
            if self.category == other.category:
                if self.package == other.package:
                    return ver_cmp(self.version, self.revision, other.version, other.revision) >= 0
                return self.package > other.package
            return self.category > other.category
        except AttributeError:
            raise TypeError(
                "'>=' not supported between instances of "
                f"{self.__class__.__name__!r} and {other.__class__.__name__!r}"
            )

    @property
    def versioned_atom(self):
        if self.version is not None:
            return atom.atom(f"={self.cpvstr}")
        return self.unversioned_atom

    @property
    def unversioned_atom(self):
        return atom.atom(self.key)

    @classmethod
    def versioned(cls, *args):
        return cls(versioned=True, *args)

    @classmethod
    def unversioned(cls, *args):
        return cls(versioned=False, *args)


class VersionedCPV(CPV):

    __slots__ = ()

    def __init__(self, *args):
        super().__init__(*args, versioned=True)


class UnversionedCPV(CPV):

    __slots__ = ()

    def __init__(self, *args):
        super().__init__(*args, versioned=False)
