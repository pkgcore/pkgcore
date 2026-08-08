"""Typed payloads for creating and updating bugs.

Bugzilla mutates list valued fields through an ``{"add": [...], "remove": [...]}``
object, and silently ignores anything it doesn't recognise, so a misspelt key
like ``cc_add`` is accepted and does nothing. :class:`ListChange` and the frozen
payload classes here make that shape the only one expressible.
"""

__all__ = (
    "MAINTAINER_NEEDED",
    "MAX_COMMENT_LENGTH",
    "MAX_SUMMARY_LENGTH",
    "TREECLEANER",
    "BugUpdate",
    "FlagChange",
    "ListChange",
    "NewBug",
    "NewComment",
    "summarise",
)

import dataclasses
import datetime
import typing

from .enums import (
    BugCategory,
    Component,
    FlagStatus,
    Product,
    Resolution,
    RuntimeTesting,
    Severity,
    Status,
)
from .errors import BugzillaUsageError
from .pkglist import PackageList
from .wire import (
    BugId,
    RawBugUpdate,
    RawFlagChange,
    RawListChange,
    RawNewBug,
    RawNewComment,
)

# bugzilla rejects longer comments with error 114
MAX_COMMENT_LENGTH: typing.Final = 65535

# the length past which a package list summary is collapsed to "and friends"
MAX_SUMMARY_LENGTH: typing.Final = 90

MAINTAINER_NEEDED: typing.Final = "maintainer-needed@gentoo.org"
TREECLEANER: typing.Final = "treecleaner@gentoo.org"


@dataclasses.dataclass(frozen=True, slots=True)
class ListChange[T]:
    """An add/remove/set mutation of a list valued field"""

    add: tuple[T, ...] = ()
    remove: tuple[T, ...] = ()
    replace: tuple[T, ...] | None = None

    def __post_init__(self) -> None:
        if self.replace is not None and (self.add or self.remove):
            raise BugzillaUsageError("replace cannot be combined with add or remove")
        if overlap := frozenset(self.add) & frozenset(self.remove):
            raise BugzillaUsageError(
                f"the same value is both added and removed: {sorted(map(str, overlap))}"
            )

    @classmethod
    def adding(cls, *values: T) -> "ListChange[T]":
        return cls(add=values)

    @classmethod
    def removing(cls, *values: T) -> "ListChange[T]":
        return cls(remove=values)

    @classmethod
    def setting(cls, *values: T) -> "ListChange[T]":
        """Replace the field wholesale, Bugzilla's ``set``"""
        return cls(replace=values)

    def __bool__(self) -> bool:
        return bool(self.add or self.remove or self.replace is not None)

    def __or__(self, other: "ListChange[T]") -> "ListChange[T]":
        if other.replace is not None:
            return other
        return ListChange(
            add=self.add + tuple(x for x in other.add if x not in self.add),
            remove=self.remove + tuple(x for x in other.remove if x not in self.remove),
        )

    def to_wire(self) -> RawListChange:
        if self.replace is not None:
            return {"set": [str(x) for x in self.replace]}
        wire: RawListChange = {}
        if self.add:
            wire["add"] = [str(x) for x in self.add]
        if self.remove:
            wire["remove"] = [str(x) for x in self.remove]
        return wire


@dataclasses.dataclass(frozen=True, slots=True)
class FlagChange:
    """Set or clear a flag"""

    name: str
    status: FlagStatus
    requestee: str | None = None

    def to_wire(self) -> RawFlagChange:
        wire: RawFlagChange = {"name": self.name, "status": self.status.value}
        if self.requestee is not None:
            wire["requestee"] = self.requestee
        return wire


@dataclasses.dataclass(frozen=True, slots=True)
class NewComment:
    """A comment to leave alongside an update"""

    body: str
    is_private: bool = False

    def __post_init__(self) -> None:
        if len(self.body) > MAX_COMMENT_LENGTH:
            raise BugzillaUsageError(
                f"comment is {len(self.body)} characters, the limit is "
                f"{MAX_COMMENT_LENGTH}; use NewComment.truncated()"
            )

    @classmethod
    def truncated(
        cls, body: str, limit: int = MAX_COMMENT_LENGTH, **kwargs: typing.Any
    ) -> "NewComment":
        """Build a comment, cutting an overlong body on a line boundary"""
        if len(body) > limit:
            marker = "\n...\n"
            head = body[: limit - len(marker)]
            body = head[: head.rfind("\n") + 1 or len(head)].rstrip() + marker
        return cls(body, **kwargs)

    def to_wire(self) -> RawNewComment:
        wire: RawNewComment = {"body": self.body}
        if self.is_private:
            wire["is_private"] = True
        return wire


def summarise(package_list: PackageList, category: BugCategory) -> str:
    """Build the conventional summary for an arch team request"""
    names = [
        pkg.cpvstr if pkg.op == "=" else str(pkg.key) for pkg in package_list.atoms
    ]
    if not names:
        raise BugzillaUsageError("cannot summarise an empty package list")
    summary = f"{', '.join(names)}: {category.summary_suffix}"
    if len(summary) > MAX_SUMMARY_LENGTH and len(names) > 1:
        summary = f"{names[0]} and friends: {category.summary_suffix}"
    return summary


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class NewBug:
    """A bug to file"""

    summary: str
    description: str
    component: Component | str
    product: Product | str = Product.GENTOO_LINUX
    version: str = "unspecified"
    severity: Severity | str = Severity.NORMAL
    assigned_to: str | None = None
    cc: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    depends_on: tuple[BugId, ...] = ()
    blocks: tuple[BugId, ...] = ()
    see_also: tuple[str, ...] = ()
    deadline: datetime.date | None = None
    package_list: PackageList | None = None
    runtime_testing_required: RuntimeTesting | None = None

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise BugzillaUsageError("a new bug needs a summary")

    @classmethod
    def arch_request(
        cls,
        category: BugCategory,
        package_list: PackageList,
        *,
        maintainers: typing.Sequence[str] = (),
        cc_arches: bool = False,
        summary: str | None = None,
        description: str | None = None,
        **kwargs: typing.Any,
    ) -> "NewBug":
        """A keywordreq or stablereq, with the bgo conventions applied"""
        assignee, *cc = maintainers or (MAINTAINER_NEEDED,)
        return cls(
            product=category.product,
            component=category.component,
            severity=Severity.ENHANCEMENT,
            summary=summary or summarise(package_list, category),
            description=description or f"Please {category.verb} the listed packages.",
            keywords=("CC-ARCHES",) if cc_arches else (),
            assigned_to=assignee,
            cc=tuple(cc),
            package_list=package_list,
            **kwargs,
        )

    @classmethod
    def package_mask(
        cls,
        summary: str,
        description: str,
        *,
        rites: int,
        maintainers: typing.Sequence[str] = (),
        today: datetime.date | None = None,
        **kwargs: typing.Any,
    ) -> "NewBug":
        """A last rites tracker, masked for ``rites`` days"""
        assignee, *cc = maintainers or (MAINTAINER_NEEDED,)
        today = today or datetime.datetime.now(datetime.UTC).date()
        return cls(
            component=Component.CURRENT_PACKAGES,
            summary=summary,
            description=description,
            keywords=("PMASKED",),
            assigned_to=assignee,
            cc=(*cc, TREECLEANER),
            deadline=today + datetime.timedelta(days=rites),
            **kwargs,
        )

    def to_wire(self) -> RawNewBug:
        wire: RawNewBug = {
            "product": str(self.product),
            "component": str(self.component),
            "summary": self.summary,
            "description": self.description,
            "version": self.version,
            "severity": str(self.severity),
        }
        if self.assigned_to:
            wire["assigned_to"] = self.assigned_to
        if self.cc:
            wire["cc"] = list(self.cc)
        if self.keywords:
            wire["keywords"] = list(self.keywords)
        if self.depends_on:
            wire["depends_on"] = list(self.depends_on)
        if self.blocks:
            wire["blocks"] = list(self.blocks)
        if self.see_also:
            wire["see_also"] = list(self.see_also)
        if self.deadline is not None:
            wire["deadline"] = self.deadline.isoformat()
        if self.package_list is not None:
            wire["cf_stabilisation_atoms"] = str(self.package_list)
        if self.runtime_testing_required is not None:
            wire["cf_runtime_testing_required"] = str(self.runtime_testing_required)
        return wire


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class BugUpdate:
    """A patch to apply to one or more bugs.

    Every field defaults to leaving the bug alone. List valued fields only
    accept a :class:`ListChange`, so the ``cc_add`` shape Bugzilla ignores is
    both a static and a runtime error.
    """

    status: Status | None = None
    resolution: Resolution | None = None
    dupe_of: BugId | None = None
    summary: str | None = None
    assigned_to: str | None = None
    whiteboard: str | None = None
    deadline: datetime.date | None = None
    cc: ListChange[str] = ListChange()
    keywords: ListChange[str] = ListChange()
    blocks: ListChange[BugId] = ListChange()
    depends_on: ListChange[BugId] = ListChange()
    see_also: ListChange[str] = ListChange()
    groups: ListChange[str] = ListChange()
    flags: tuple[FlagChange, ...] = ()
    comment: NewComment | None = None
    package_list: PackageList | None = None
    runtime_testing_required: RuntimeTesting | None = None

    def __post_init__(self) -> None:
        if self.resolution is not None and self.status is None:
            raise BugzillaUsageError("a resolution needs an explicit status")
        if self.status is Status.RESOLVED and self.resolution is None:
            raise BugzillaUsageError("status=RESOLVED needs a resolution")
        if (self.resolution is Resolution.DUPLICATE) != (self.dupe_of is not None):
            raise BugzillaUsageError("DUPLICATE and dupe_of must be used together")

    def __bool__(self) -> bool:
        return any(
            bool(getattr(self, field.name)) for field in dataclasses.fields(self)
        )

    @classmethod
    def sanity_check(
        cls, status: bool | None, *, comment: str | None = None, **kwargs: typing.Any
    ) -> "BugUpdate":
        """Set the sanity-check flag, None clearing it"""
        flag = {
            True: FlagStatus.GRANTED,
            False: FlagStatus.DENIED,
            None: FlagStatus.CLEARED,
        }
        return cls(
            flags=(FlagChange("sanity-check", flag[status]),),
            comment=NewComment(comment) if comment is not None else None,
            **kwargs,
        )

    @classmethod
    def resolve(
        cls,
        resolution: Resolution = Resolution.FIXED,
        *,
        comment: str | None = None,
        **kwargs: typing.Any,
    ) -> "BugUpdate":
        return cls(
            status=Status.RESOLVED,
            resolution=resolution,
            comment=NewComment(comment) if comment is not None else None,
            **kwargs,
        )

    @classmethod
    def obsoleted_by(cls, bug: BugId | int, **kwargs: typing.Any) -> "BugUpdate":
        """Close as OBSOLETE, pointing at the bug that supersedes this one"""
        return cls(
            status=Status.RESOLVED,
            resolution=Resolution.OBSOLETE,
            see_also=ListChange.adding(f"https://bugs.gentoo.org/{bug}"),
            **kwargs,
        )

    def to_wire(self, ids: typing.Sequence[BugId | int]) -> RawBugUpdate:
        """Render the payload.

        The complete id list is always sent, since Bugzilla lets the body
        override the id in the request path rather than the other way around.
        """
        if not ids:
            raise BugzillaUsageError("an update needs at least one bug id")
        wire: RawBugUpdate = {"ids": [BugId(int(x)) for x in ids]}
        if self.status is not None:
            wire["status"] = str(self.status)
        if self.resolution is not None:
            wire["resolution"] = str(self.resolution)
        if self.dupe_of is not None:
            wire["dupe_of"] = self.dupe_of
        if self.summary is not None:
            wire["summary"] = self.summary
        if self.assigned_to is not None:
            wire["assigned_to"] = self.assigned_to
        if self.whiteboard is not None:
            wire["whiteboard"] = self.whiteboard
        if self.deadline is not None:
            wire["deadline"] = self.deadline.isoformat()
        for name in ("cc", "keywords", "blocks", "depends_on", "see_also", "groups"):
            if change := typing.cast(ListChange[typing.Any], getattr(self, name)):
                wire[name] = change.to_wire()
        if self.flags:
            wire["flags"] = [x.to_wire() for x in self.flags]
        if self.comment is not None:
            wire["comment"] = self.comment.to_wire()
        if self.package_list is not None:
            wire["cf_stabilisation_atoms"] = str(self.package_list)
        if self.runtime_testing_required is not None:
            wire["cf_runtime_testing_required"] = str(self.runtime_testing_required)
        return wire
