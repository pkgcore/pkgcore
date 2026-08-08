"""Immutable value objects for what bugs.gentoo.org hands back.

Each :class:`Bug` field carries the wire name it came from and how to decode
it, so :data:`INCLUDE_FIELDS` and :func:`parse_bug` are both derived from the
one declaration and can't drift apart.
"""

__all__ = (
    "INCLUDE_FIELDS",
    "Bug",
    "BugChanges",
    "Comment",
    "FieldChange",
    "Flag",
    "User",
    "parse_bug",
    "parse_changes",
    "parse_comment",
    "parse_user",
)

import dataclasses
import datetime
import typing

from ..log import logger
from .enums import BugCategory, FlagStatus, Product, RuntimeTesting
from .pkglist import PackageList
from .wire import (
    BugId,
    CommentId,
    FlagId,
    FlagTypeId,
    RawBug,
    RawChanges,
    RawComment,
    RawFlag,
    RawWhoami,
)

_EPOCH: typing.Final = datetime.datetime.fromtimestamp(0, datetime.UTC)
_NO_FLAG_ID: typing.Final = FlagId(0)
_NO_FLAG_TYPE_ID: typing.Final = FlagTypeId(0)


def _field[T](wire: str, parse: typing.Callable[[typing.Any], T], default: T) -> T:
    """Declare a field along with its wire name and decoder.

    Returns ``T`` rather than ``Field[T]`` for the same reason
    :func:`dataclasses.field` returns ``Any``, so the class body stays readable.
    """
    return dataclasses.field(default=default, metadata={"wire": wire, "parse": parse})


def _strs(value: typing.Any) -> tuple[str, ...]:
    return tuple(value)


def _ids(value: typing.Any) -> tuple[BugId, ...]:
    return tuple(BugId(x) for x in value)


def _datetime(value: typing.Any) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


def _date(value: typing.Any) -> datetime.date | None:
    return datetime.date.fromisoformat(value) if value else None


def _runtime_testing(value: typing.Any) -> RuntimeTesting:
    try:
        return RuntimeTesting(str(value).capitalize())
    except ValueError:
        return RuntimeTesting.UNSET


@dataclasses.dataclass(frozen=True, slots=True)
class Flag:
    """A flag set on a bug"""

    name: str
    status: FlagStatus
    id: FlagId = _NO_FLAG_ID
    type_id: FlagTypeId = _NO_FLAG_TYPE_ID
    setter: str = ""
    requestee: str = ""

    @property
    def granted(self) -> bool | None:
        """Tri-state view: True for ``+``, False for ``-``, None otherwise"""
        if self.status is FlagStatus.GRANTED:
            return True
        if self.status is FlagStatus.DENIED:
            return False
        return None


def _flags(value: typing.Any) -> tuple[Flag, ...]:
    return tuple(parse_flag(x) for x in value)


def parse_flag(raw: RawFlag) -> Flag:
    return Flag(
        name=raw["name"],
        status=FlagStatus(raw["status"]),
        id=raw.get("id", _NO_FLAG_ID),
        type_id=raw.get("type_id", _NO_FLAG_TYPE_ID),
        setter=raw.get("setter", ""),
        requestee=raw.get("requestee", ""),
    )


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Bug:
    """An immutable snapshot of a bug.

    Anonymous requests get every email address truncated at the ``@``, so
    :attr:`assigned_to`, :attr:`creator` and :attr:`cc` only hold full
    addresses when the client was given an api key.
    """

    id: BugId = _field("id", BugId, BugId(0))
    summary: str = _field("summary", str, "")
    product: str = _field("product", str, "")
    component: str = _field("component", str, "")
    version: str = _field("version", str, "")
    status: str = _field("status", str, "")
    resolution: str = _field("resolution", str, "")
    severity: str = _field("severity", str, "")
    priority: str = _field("priority", str, "")
    assigned_to: str = _field("assigned_to", str, "")
    creator: str = _field("creator", str, "")
    cc: tuple[str, ...] = _field("cc", _strs, ())
    keywords: tuple[str, ...] = _field("keywords", _strs, ())
    whiteboard: str = _field("whiteboard", str, "")
    alias: tuple[str, ...] = _field("alias", _strs, ())
    tags: tuple[str, ...] = _field("tags", _strs, ())
    depends_on: tuple[BugId, ...] = _field("depends_on", _ids, ())
    blocks: tuple[BugId, ...] = _field("blocks", _ids, ())
    see_also: tuple[str, ...] = _field("see_also", _strs, ())
    groups: tuple[str, ...] = _field("groups", _strs, ())
    flags: tuple[Flag, ...] = _field("flags", _flags, ())
    deadline: datetime.date | None = _field("deadline", _date, None)
    creation_time: datetime.datetime = _field("creation_time", _datetime, _EPOCH)
    last_change_time: datetime.datetime = _field("last_change_time", _datetime, _EPOCH)
    package_list: PackageList = _field(
        "cf_stabilisation_atoms", PackageList, PackageList()
    )
    runtime_testing_required: RuntimeTesting = _field(
        "cf_runtime_testing_required", _runtime_testing, RuntimeTesting.UNSET
    )

    @property
    def category(self) -> BugCategory | None:
        return BugCategory.from_product_component(self.product, self.component)

    @property
    def resolved(self) -> bool:
        return bool(self.resolution)

    @property
    def security(self) -> bool:
        """Whether the bug lives in the security product.

        Orthogonal to carrying the ``SECURITY`` keyword, which marks an
        ordinary bug as blocking a security one.
        """
        return self.product == Product.GENTOO_SECURITY

    @property
    def sanity_check(self) -> bool | None:
        return self.flag("sanity-check")

    def flag(self, name: str) -> bool | None:
        """Tri-state status of a named flag, None when it isn't set"""
        for flag in self.flags:
            if flag.name == name:
                return flag.granted
        return None

    def arches(self, known_arches: typing.Container[str]) -> tuple[str, ...]:
        """Arch names found in CC, tolerating truncated anonymous addresses"""
        return tuple(
            name
            for entry in self.cc
            if (entry.endswith("@gentoo.org") or "@" not in entry)
            and (name := entry.split("@", 1)[0]) in known_arches
        )

    @property
    def url(self) -> str:
        return f"https://bugs.gentoo.org/{self.id}"


_SPECS: typing.Final = tuple(
    (field.name, field.metadata["wire"], field.metadata["parse"])
    for field in dataclasses.fields(Bug)
    if "wire" in field.metadata
)

INCLUDE_FIELDS: typing.Final[tuple[str, ...]] = tuple(
    dict.fromkeys(wire for _, wire, _ in _SPECS)
)


def parse_bug(raw: RawBug) -> Bug:
    """Build a :class:`Bug` from a raw response, skipping absent fields"""
    data = typing.cast(dict[str, typing.Any], raw)
    kwargs: dict[str, typing.Any] = {}
    for name, wire, parse in _SPECS:
        if wire not in data:
            logger.debug("bug %s: field %r absent from response", data.get("id"), wire)
        elif (value := data[wire]) is not None:
            kwargs[name] = parse(value)
    # tie the package list back to its bug, so a parse failure says which one
    if (pkglist := kwargs.get("package_list")) is not None and "id" in kwargs:
        kwargs["package_list"] = PackageList(pkglist.text, bug_id=kwargs["id"])
    return Bug(**kwargs)


@dataclasses.dataclass(frozen=True, slots=True)
class Comment:
    """A single comment on a bug"""

    id: CommentId
    bug_id: BugId
    count: int
    text: str
    creator: str
    creation_time: datetime.datetime
    is_private: bool = False
    tags: tuple[str, ...] = ()

    @property
    def obsolete(self) -> bool:
        return "obsolete" in self.tags


def parse_comment(raw: RawComment) -> Comment:
    return Comment(
        id=raw["id"],
        bug_id=raw["bug_id"],
        count=raw["count"],
        text=raw["text"],
        creator=raw["creator"],
        creation_time=_datetime(raw["creation_time"]),
        is_private=raw.get("is_private", False),
        tags=tuple(raw.get("tags", ())),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class User:
    """The account an api key belongs to"""

    id: int
    name: str
    real_name: str = ""


def parse_user(raw: RawWhoami) -> User:
    return User(id=raw["id"], name=raw["name"], real_name=raw.get("real_name", ""))


@dataclasses.dataclass(frozen=True, slots=True)
class FieldChange:
    """What one field gained and lost in an update"""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class BugChanges:
    """The result of updating a bug"""

    id: BugId
    last_change_time: datetime.datetime
    changes: dict[str, FieldChange] = dataclasses.field(default_factory=dict)
    alias: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.changes)


def _split_change(value: str) -> tuple[str, ...]:
    # bugzilla joins these with ", " rather than returning a list
    return tuple(x for x in (part.strip() for part in value.split(",")) if x)


def parse_changes(raw: RawChanges) -> BugChanges:
    return BugChanges(
        id=raw["id"],
        last_change_time=_datetime(raw["last_change_time"]),
        changes={
            name: FieldChange(
                added=_split_change(change.get("added", "")),
                removed=_split_change(change.get("removed", "")),
            )
            for name, change in raw.get("changes", {}).items()
        },
        alias=tuple(raw.get("alias", ())),
    )
