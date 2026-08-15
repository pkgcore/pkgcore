"""Resolving a keywording or stabilization request against a repo.

A request is a list of package specs, each with the arches it asks for, in the
form Gentoo's arch teams use::

    =dev-libs/foo-1.2.3 amd64 x86    # stabilize this exact version
    dev-libs/bar        ~ppc64       # keyword any suitable version

Three keyword sentinels are understood: :data:`ALL_KEYWORDS` expands to the
arches the package could plausibly be requested for, :data:`SAME_KEYWORDS`
repeats the line above, and :data:`NO_KEYWORDS` skips the line.

:func:`match_packages` turns that into concrete packages and arches. It knows
nothing about where the request came from; :meth:`pkgcore.bugzilla.Bug.match_packages`
is the binding for one that came off a bug.
"""

__all__ = (
    "ALL_KEYWORDS",
    "NO_KEYWORDS",
    "SAME_KEYWORDS",
    "KeywordNoMatch",
    "KeywordNoneLeft",
    "KeywordNotSpecified",
    "KeywordRequest",
    "PackageInvalid",
    "PackageListDoneAlready",
    "PackageListEmpty",
    "PackageMatchException",
    "PackageNoMatch",
    "can_stabilize_allarches",
    "filter_prefix_keywords",
    "match_packages",
    "select_best_version",
    "suggested_keywords",
)

import typing

from ..exceptions import PkgcoreException
from .misc import sort_keywords

if typing.TYPE_CHECKING:
    from .atom import atom
    from .ebuild_src import package
    from .repository import UnconfiguredTree

ALL_KEYWORDS: typing.Final = "*"
SAME_KEYWORDS: typing.Final = "^"
NO_KEYWORDS: typing.Final = "-"


class PackageMatchException(PkgcoreException):
    """The request can't be resolved as written.

    Callers routinely catch this broadly to report a request as unusable, which
    is why :class:`KeywordNoneLeft` deliberately sits outside it.
    """


class PackageInvalid(PackageMatchException):
    """A spec isn't one this kind of request may carry"""


class PackageNoMatch(PackageMatchException):
    """A spec parses but matches nothing in the repo"""


class KeywordNoMatch(PackageMatchException):
    """A keyword isn't known to the repo, or a sentinel can't be resolved"""


class KeywordNotSpecified(PackageMatchException):
    """Some packages were left without keywords"""

    def __init__(self, packages: typing.Iterable[str], message: str = "") -> None:
        self.packages = tuple(packages)
        super().__init__(
            message or f"incomplete keywords for packages: {' '.join(self.packages)}"
        )


class PackageListEmpty(PackageMatchException):
    """Nothing was left to act on"""


class PackageListDoneAlready(PackageListEmpty):
    """Nothing was left because every package is keyworded already"""


class KeywordNoneLeft(PkgcoreException):
    """No keywords were given and there are none left to suggest.

    Deliberately not a :class:`PackageMatchException`: the request is fine, it
    simply has nothing to do, and a caller reporting broken requests must not
    treat this as one.
    """


class KeywordRequest(typing.NamedTuple):
    """A matched package and the arches requested for it"""

    pkg: "package"
    keywords: list[str]


def select_best_version(matches: typing.Iterable["package"]) -> "package | None":
    """Pick the version a request without an exact one should act on.

    The newest keyworded version wins; failing that the newest non-live one,
    since a live ebuild is never what a keywording request means.

    :param matches: candidate packages, in any order
    :return: the version to act on, or None if there were no candidates
    """
    ordered = sorted(matches, reverse=True)
    for suitable in (lambda p: bool(p.keywords), lambda p: not p.live, lambda p: True):
        for pkg in ordered:
            if suitable(pkg):
                return pkg
    return None


def filter_prefix_keywords(keywords: typing.Iterable[str]) -> list[str]:
    """Drop prefix keywords, e.g. ``x86-macos`` or ``*-fbsd``"""
    return [x for x in keywords if "-" not in x]


def suggested_keywords(
    repo: "UnconfiguredTree", pkg: "package", *, stable: bool
) -> frozenset[str]:
    """The arches :data:`ALL_KEYWORDS` expands to for ``pkg``.

    Stabilizing, that is the arches already stable on some other version and
    ``~arch`` on this one. Keywording, it is the arches present on some other
    version and missing here. Prefix keywords are never suggested.

    :param repo: repo to look for the package's other versions in
    :param pkg: the version the request names
    :param stable: whether the request is a stabilization
    :return: the arches to request, unordered
    """
    disallowed = "-~" if stable else "-"
    candidates = {
        x.lstrip("~")
        for other in repo.match(pkg.unversioned_atom)
        for x in other.keywords
        if x[0] not in disallowed
    }
    if stable:
        # a version can only go stable where it is currently testing
        candidates &= {x.lstrip("~") for x in pkg.keywords if x[0] == "~"}
    else:
        candidates -= {x.lstrip("~-") for x in pkg.keywords}
    return frozenset(filter_prefix_keywords(candidates))


def can_stabilize_allarches(
    repo: "UnconfiguredTree",
    requests: typing.Iterable[tuple["package", typing.Iterable[str]]],
) -> bool:
    """Whether every package already has a stable version on every arch asked for.

    That is the precondition for one arch team stabilizing on behalf of all of
    them: nobody is being asked to take on an arch they never had.

    :param repo: repo to look for the packages' other versions in
    :param requests: packages paired with the arches asked for
    :return: whether an all-arches stabilization is permissible
    """
    for pkg, keywords in requests:
        left = set(keywords)
        for other in repo.itermatch(pkg.unversioned_atom):
            # ~arch and -arch simply won't match, so they need no filtering
            left.difference_update(other.keywords)
        if left:
            return False
    return True


def match_packages(
    repo: "UnconfiguredTree",
    requested: typing.Iterable[tuple["atom", typing.Sequence[str]]],
    *,
    stable: bool,
    cc_arches: typing.Sequence[str] = (),
    only_new: bool = False,
    filter_arch: typing.Iterable[str] = (),
    allarches: bool = False,
) -> typing.Iterator[KeywordRequest]:
    """Match ``requested`` specs against ``repo``, yielding packages and arches.

    :param repo: repo to resolve the specs against
    :param requested: each package spec paired with the keywords written for
        it, in order, since :data:`SAME_KEYWORDS` refers to the line above
    :param stable: select stabilization semantics: only ``=`` specs are
        allowed, and :data:`ALL_KEYWORDS` means "arches stable elsewhere"
        rather than "arches keyworded elsewhere"
    :param cc_arches: the arches the request is addressed to.  A line with no
        keywords of its own inherits them; a line with keywords is narrowed to
        them, and one left with nothing is skipped
    :param only_new: drop the arches the package already carries
    :param filter_arch: keep only the arches listed
    :param allarches: re-add every candidate arch on top of ``filter_arch``,
        for an all-arches stabilization
    :return: the matched packages, each with the arches to request for it
    :raises PackageMatchException: if the request can't be resolved
    :raises KeywordNoneLeft: if nothing was specified and nothing is left
    """
    valid_arches = frozenset(repo.known_arches)
    cc_arches = tuple(cc_arches)
    filter_arch = frozenset(filter_arch)

    keyworded_already = filtered = yielded = False
    no_potential_keywords: list[str] = []
    no_keywords: list[str] = []
    previous: list[str] | None = None

    for dep, written in requested:
        if stable and (dep.op != "=" or dep.slot):
            raise PackageInvalid(f"disallowed package spec (only = allowed): {dep}")
        # a stabilization spec is an exact =cpv, so it matches at most one
        matched = repo.match(dep)
        pkg = matched[0] if stable and matched else select_best_version(matched)
        if pkg is None:
            raise PackageNoMatch(f"no match for package: {dep}")

        keywords = [x.strip().lstrip("~") for x in written]
        if NO_KEYWORDS in keywords:
            continue
        if ALL_KEYWORDS in keywords:
            keywords = sort_keywords(suggested_keywords(repo, pkg, stable=stable)) + [
                x for x in keywords if x != ALL_KEYWORDS
            ]
        if SAME_KEYWORDS in keywords:
            if previous is None:
                raise KeywordNoMatch(f"invalid use of {SAME_KEYWORDS} on first line")
            keywords = previous + [x for x in keywords if x != SAME_KEYWORDS]

        if unknown := frozenset(keywords) - valid_arches:
            raise KeywordNoMatch(f"incorrect keywords: {' '.join(sorted(unknown))}")

        if not keywords:
            keywords = list(cc_arches)
        elif cc_arches:
            keywords = [x for x in keywords if x in cc_arches]
            # the line is no longer addressed to anyone
            if not keywords:
                continue

        if not keywords:
            if suggested_keywords(repo, pkg, stable=stable):
                no_keywords.append(str(dep))
            else:
                no_potential_keywords.append(str(dep))
            yield KeywordRequest(pkg, keywords)
            continue
        previous = keywords

        # still filtered by arch, since the arches asked for may be disjoint
        # with the all-arches candidates
        allarches_kw: list[str] = []
        if allarches and stable and filter_arch:
            allarches_kw = sort_keywords(suggested_keywords(repo, pkg, stable=True))

        if only_new:
            keywords = [
                k
                for k in keywords
                if k not in pkg.keywords and (stable or f"~{k}" not in pkg.keywords)
            ]
            if not keywords:
                keyworded_already = True
                continue

        if filter_arch:
            keywords = [k for k in keywords if k in filter_arch]
            keywords += [k for k in allarches_kw if k not in keywords]
            if not keywords:
                filtered = True
                continue

        yield KeywordRequest(pkg, keywords)
        yielded = True

    if no_keywords:
        raise KeywordNotSpecified(no_keywords)
    if no_potential_keywords:
        # only worth reporting as "nothing left" if nothing else came out
        if yielded:
            raise KeywordNotSpecified(no_potential_keywords)
        raise KeywordNoneLeft(
            "package keywords in line with other versions and none specified"
        )
    if not yielded:
        if filtered:
            raise PackageListEmpty("no packages match requested arch")
        if keyworded_already:
            raise PackageListDoneAlready("all packages keyworded already")
        raise PackageListEmpty("empty package list")
