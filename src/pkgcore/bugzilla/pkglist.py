"""Parsing and rewriting of the ``cf_stabilisation_atoms`` bug field.

The field is a newline separated list of ``<package spec> [keyword...]`` lines,
with ``#`` comments and three keyword sentinels: ``*`` expands to the keywords
suggested for that package, ``^`` repeats the previous line's keywords, and
``-`` marks a line as deliberately having none.

:class:`PackageList` keeps the original text and rewrites only the lines it has
to, so indentation and comments on untouched lines survive a round trip.
"""

__all__ = (
    "ALL_KEYWORDS",
    "NO_KEYWORDS",
    "SAME_KEYWORDS",
    "PackageList",
    "PackageListEntry",
    "parse_atom",
)

import dataclasses
import re
import typing

from snakeoil.klass import immutable
from snakeoil.klass.properties import jit_attr_none

from ..ebuild.atom import atom
from ..ebuild.errors import MalformedAtom
from ..ebuild.keywording import ALL_KEYWORDS, NO_KEYWORDS, SAME_KEYWORDS
from .errors import PackageListError
from .wire import BugId

_COMMENT_RE: typing.Final = re.compile(r"(?:^|\s)#")
_TOKEN_RE: typing.Final = re.compile(r"\S+")


def parse_atom(token: str) -> atom:
    """Parse a package list token into an atom.

    Stabilization lines carry a bare ``cat/pkg-1.2.3`` rather than the
    ``=cat/pkg-1.2.3`` an atom needs, so the versioned form is tried first.

    A package list names packages to act on, so the qualifiers that would make
    that ambiguous are rejected: blockers, use deps, slot operators and repo
    ids all mean something the list has no way to honour.

    :param token: the first whitespace separated field of a list line
    :return: the atom the token names
    :raises MalformedAtom: if the token isn't a usable package spec
    """
    for candidate in (f"={token}", token):
        try:
            pkg = atom(candidate)
        except MalformedAtom:
            continue
        if pkg.blocks or pkg.use or pkg.slot_operator or pkg.repo_id:
            raise MalformedAtom(
                token, "blockers, use deps, slot operators and repo ids"
            )
        return pkg
    raise MalformedAtom(token)


@dataclasses.dataclass(frozen=True, slots=True)
class PackageListEntry:
    """A single line of a package list"""

    lineno: int
    raw: str
    pkg: atom | None
    keywords: tuple[str, ...] = ()
    comment: str = ""
    eol: str = ""

    @property
    def is_blank(self) -> bool:
        return self.pkg is None

    def with_keywords(self, keywords: typing.Iterable[str]) -> "PackageListEntry":
        """Return a copy with new keywords, rewriting only the keyword text.

        The rest of the line survives as written: the spec in its original
        spelling, the alignment around it, and the comment.

        :param keywords: the keywords to write in place of the current ones
        :return: the rewritten entry, or ``self`` if the line holds no spec
        """
        if self.pkg is None:
            return self
        keywords = tuple(keywords)
        comment_at = len(self.raw)
        if match := _COMMENT_RE.search(self.raw):
            comment_at = match.end() - 1
        body = self.raw[:comment_at]
        if not (tokens := list(_TOKEN_RE.finditer(body))):
            return self
        # anchoring on the tokens keeps the whitespace on either side of them
        if len(tokens) > 1:
            head = body[: tokens[1].start()]
        else:
            head = body[: tokens[0].end()] + (" " if keywords else "")
        return dataclasses.replace(
            self,
            keywords=keywords,
            raw=(
                f"{head}{' '.join(keywords)}"
                f"{body[tokens[-1].end() :]}{self.raw[comment_at:]}"
            ),
        )


class PackageList(immutable.Simple):
    """A lazily parsed view of a bug's package list.

    Parsing is deferred so fetching a bug with a malformed list never fails;
    only code that looks at the list does.
    """

    __slots__ = ("_entries", "bug_id", "text")

    def __init__(self, text: str = "", *, bug_id: BugId | None = None) -> None:
        self.text = text
        self.bug_id = bug_id

    @classmethod
    def build(
        cls, entries: typing.Iterable[tuple[atom, typing.Iterable[str]]]
    ) -> "PackageList":
        """Construct a fresh list from atoms and their keywords"""
        return cls(
            "\n".join(
                " ".join((str(pkg), *keywords)).rstrip() for pkg, keywords in entries
            )
        )

    @jit_attr_none
    def entries(self) -> tuple[PackageListEntry, ...]:
        """Every line of the list, blanks and comments included"""
        return tuple(self._parse())

    def _parse(self) -> typing.Iterator[PackageListEntry]:
        for lineno, line in enumerate(self.text.splitlines(keepends=True), start=1):
            raw = line.rstrip("\r\n")
            eol = line[len(raw) :]
            body = raw
            comment = ""
            if match := _COMMENT_RE.search(body):
                comment, body = body[match.end() - 1 :], body[: match.start()]
            if not (tokens := body.split()):
                yield PackageListEntry(lineno, raw, None, comment=comment, eol=eol)
                continue
            try:
                pkg = parse_atom(tokens[0])
            except MalformedAtom as exc:
                raise PackageListError(
                    str(exc), bug_id=self.bug_id, lineno=lineno, line=raw
                ) from exc
            yield PackageListEntry(lineno, raw, pkg, tuple(tokens[1:]), comment, eol)

    @property
    def atoms(self) -> tuple[atom, ...]:
        return tuple(x.pkg for x in self.entries if x.pkg is not None)

    def keywords_for(self, pkg: atom) -> tuple[str, ...]:
        """Keywords requested for an atom, as written"""
        for entry in self.entries:
            if entry.pkg == pkg:
                return entry.keywords
        return ()

    def expand(
        self, suggest: typing.Callable[[atom], typing.Sequence[str]]
    ) -> "PackageList":
        """Resolve the ``*`` and ``^`` sentinels.

        Only the lines that change are rewritten, and each keeps everything but
        its keywords, so the result can go straight back onto the bug.

        :param suggest: returns the keywords a package should be requested
            for, in the order they should be written; returning nothing
            collapses the line to ``-``.  Which version to suggest for is the
            caller's to decide
        :return: the expanded list, or ``self`` if nothing needed rewriting
        :raises PackageListError: on a ``^`` with nothing above it to copy, or
            one that would copy nothing onto a line asking for keywords
        """
        expanded: list[PackageListEntry] = []
        previous: tuple[str, ...] | None = None
        changed = False
        for entry in self.entries:
            if entry.pkg is None:
                expanded.append(entry)
                continue
            keywords: list[str] = []
            for keyword in entry.keywords:
                if keyword == ALL_KEYWORDS:
                    keywords.extend(suggest(entry.pkg) or (NO_KEYWORDS,))
                elif keyword == SAME_KEYWORDS:
                    if previous is None:
                        raise PackageListError(
                            f"{SAME_KEYWORDS!r} keyword with no line above it",
                            bug_id=self.bug_id,
                            lineno=entry.lineno,
                            line=entry.raw,
                        )
                    # copying nothing onto a line that asks for something else
                    # is a request no rewriting can satisfy
                    if not previous and len(entry.keywords) > 1:
                        raise PackageListError(
                            f"{SAME_KEYWORDS!r} keyword copies an empty line, "
                            "but the line has keywords of its own",
                            bug_id=self.bug_id,
                            lineno=entry.lineno,
                            line=entry.raw,
                        )
                    keywords.extend(previous)
                else:
                    keywords.append(keyword)
            previous = tuple(keywords)
            if previous != entry.keywords:
                entry = entry.with_keywords(previous)
                changed = True
            expanded.append(entry)
        if not changed:
            return self
        return PackageList("".join(x.raw + x.eol for x in expanded), bug_id=self.bug_id)

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        return bool(self.text.strip())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PackageList):
            return self.text == other.text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.text!r}>"
