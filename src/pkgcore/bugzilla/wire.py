"""Literal mirrors of the bugs.gentoo.org REST JSON payloads.

Nothing here has behaviour; it exists so the rest of pkgcore.bugzilla can be
checked against the actual wire format. Note that RawBugUpdate has no cc_add
key and RawNewBug has no ids key, so the shapes that Bugzilla silently ignores
can't be constructed.
"""

__all__ = (
    "BugId",
    "CommentId",
    "FlagId",
    "FlagStatusRead",
    "FlagStatusWrite",
    "FlagTypeId",
    "JSONValue",
    "RawBug",
    "RawBugUpdate",
    "RawChanges",
    "RawComment",
    "RawComments",
    "RawCommentsResponse",
    "RawCreateResponse",
    "RawError",
    "RawFieldChange",
    "RawFlag",
    "RawFlagChange",
    "RawGetResponse",
    "RawListChange",
    "RawNewBug",
    "RawNewComment",
    "RawSearchResponse",
    "RawUpdateResponse",
    "RawWhoami",
    "RequestBody",
)

import typing

type JSONValue = (
    None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]
)

# what a request body may be; a Mapping rather than a dict so the TypedDicts
# below are accepted, which an invariant dict[str, JSONValue] would not be
type RequestBody = typing.Mapping[str, typing.Any]

BugId = typing.NewType("BugId", int)
CommentId = typing.NewType("CommentId", int)
FlagId = typing.NewType("FlagId", int)
FlagTypeId = typing.NewType("FlagTypeId", int)

FlagStatusRead = typing.Literal["?", "+", "-"]
FlagStatusWrite = typing.Literal["?", "+", "-", "X"]


class RawFlag(typing.TypedDict):
    id: FlagId
    name: str
    status: FlagStatusRead
    type_id: FlagTypeId
    setter: str
    creation_date: str
    modification_date: str
    requestee: typing.NotRequired[str]


class RawBug(typing.TypedDict, total=False):
    """A bug as returned by Bugzilla.

    Every key is optional because Bugzilla omits whatever isn't named in
    include_fields; presence is guaranteed by bug.INCLUDE_FIELDS instead.
    """

    id: BugId
    summary: str
    product: str
    component: str
    version: str
    status: str
    resolution: str
    severity: str
    priority: str
    assigned_to: str
    creator: str
    cc: list[str]
    keywords: list[str]
    whiteboard: str
    alias: list[str]
    tags: list[str]
    depends_on: list[BugId]
    blocks: list[BugId]
    see_also: list[str]
    groups: list[str]
    flags: list[RawFlag]
    deadline: str | None
    creation_time: str
    last_change_time: str
    cf_stabilisation_atoms: str
    cf_runtime_testing_required: str


class RawSearchResponse(typing.TypedDict):
    bugs: list[RawBug]


class RawGetResponse(typing.TypedDict):
    """GET /rest/bug/{id}, which unlike a search also carries faults"""

    bugs: list[RawBug]
    faults: list[dict[str, typing.Any]]


class RawComment(typing.TypedDict):
    id: CommentId
    bug_id: BugId
    count: int
    text: str
    creator: str
    time: str
    creation_time: str
    is_private: bool
    tags: list[str]
    attachment_id: typing.NotRequired[int | None]
    raw_text: typing.NotRequired[str]


class RawComments(typing.TypedDict):
    comments: list[RawComment]


class RawCommentsResponse(typing.TypedDict):
    """Note that the keys of bugs are stringified bug ids"""

    bugs: dict[str, RawComments]
    comments: dict[str, RawComment]


class RawCreateResponse(typing.TypedDict):
    id: BugId


class RawFieldChange(typing.TypedDict):
    """A single field's delta; both values are comma-and-space joined strings"""

    added: str
    removed: str


class RawChanges(typing.TypedDict):
    id: BugId
    alias: list[str]
    last_change_time: str
    changes: dict[str, RawFieldChange]


class RawUpdateResponse(typing.TypedDict):
    bugs: list[RawChanges]


class RawWhoami(typing.TypedDict):
    id: int
    name: str
    real_name: str


class RawError(typing.TypedDict):
    error: bool
    code: int
    message: str
    documentation: typing.NotRequired[str]


class RawListChange(typing.TypedDict, total=False):
    add: list[str]
    remove: list[str]
    set: list[str]


class RawFlagChange(typing.TypedDict, total=False):
    name: str
    status: FlagStatusWrite
    id: FlagId
    type_id: FlagTypeId
    requestee: str
    new: bool


class RawNewComment(typing.TypedDict, total=False):
    body: str
    is_private: bool


class RawBugUpdate(typing.TypedDict, total=False):
    ids: list[BugId]
    status: str
    resolution: str
    dupe_of: BugId
    summary: str
    assigned_to: str
    whiteboard: str
    deadline: str
    cc: RawListChange
    keywords: RawListChange
    blocks: RawListChange
    depends_on: RawListChange
    see_also: RawListChange
    groups: RawListChange
    flags: list[RawFlagChange]
    comment: RawNewComment
    cf_stabilisation_atoms: str
    cf_runtime_testing_required: str


class RawNewBug(typing.TypedDict, total=False):
    product: str
    component: str
    summary: str
    description: str
    version: str
    severity: str
    assigned_to: str
    cc: list[str]
    keywords: list[str]
    depends_on: list[BugId]
    blocks: list[BugId]
    see_also: list[str]
    deadline: str
    cf_stabilisation_atoms: str
    cf_runtime_testing_required: str
