"""The bugs.gentoo.org client."""

__all__ = ("DEFAULT_URL", "EVERYTHING", "PAGE_SIZE", "Bugzilla")

import typing
import urllib.parse
import urllib.request

from ..log import logger
from .bug import (
    INCLUDE_FIELDS,
    Bug,
    BugChanges,
    Comment,
    User,
    parse_bug,
    parse_changes,
    parse_comment,
    parse_user,
)
from .changes import BugUpdate, ListChange, NewBug
from .errors import BugzillaNotFound, BugzillaSchemaError, BugzillaUsageError
from .query import BugQuery
from .transport import AuthMode, Transport, UrllibTransport, expect_list, expect_object
from .wire import BugId, CommentId, RawBug

DEFAULT_URL: typing.Final = "https://bugs.gentoo.org"

# an unconstrained search, the default for search()/raw_search()
EVERYTHING: typing.Final = BugQuery()

# bugzilla silently clamps results at max_search_results and reports no total,
# so searches page explicitly until a short page comes back
PAGE_SIZE: typing.Final = 500


class Bugzilla:
    """A Bugzilla instance, defaulting to bugs.gentoo.org.

    Without an api key the client is read only, and Bugzilla truncates every
    email address it returns at the ``@``, so anything matching on addresses
    needs one.

    ``user_agent`` names the calling tool; it is prepended to pkgcore's own
    token rather than replacing it.
    """

    __slots__ = ("_transport", "_user", "base_url")

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_URL,
        timeout: float = 30.0,
        retries: int = 3,
        auth_mode: AuthMode = AuthMode.QUERY,
        retry_writes: bool = False,
        user_agent: str | None = None,
        opener: urllib.request.OpenerDirector | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport: Transport = transport or UrllibTransport(
            self.base_url,
            api_key,
            timeout=timeout,
            retries=retries,
            auth_mode=auth_mode,
            retry_writes=retry_writes,
            user_agent=user_agent,
            opener=opener,
        )
        self._user: User | None = None

    def whoami(self) -> User:
        """The account the api key belongs to, cached for the session"""
        if self._user is None:
            payload = self._transport.request("GET", "whoami")
            self._user = parse_user(
                typing.cast(typing.Any, expect_object(payload, "whoami"))
            )
        return self._user

    @typing.overload
    def get(self, bugs: BugId | int, /) -> Bug: ...

    @typing.overload
    def get(self, bugs: typing.Iterable[BugId | int], /) -> dict[BugId, Bug]: ...

    def get(self, bugs: typing.Any, /) -> typing.Any:
        """Fetch one bug, or a mapping for several.

        :raises BugzillaNotFound: when a single requested bug doesn't exist
        """
        if isinstance(bugs, int):
            found = self.search(BugQuery.ids((bugs,)))
            if (bug := found.get(BugId(bugs))) is None:
                raise BugzillaNotFound(f"bug {bugs} does not exist", code=101)
            return bug
        return self.search(BugQuery.ids(bugs))

    def search(self, query: BugQuery = EVERYTHING, /) -> dict[BugId, Bug]:
        """Run a search, batching and paging as needed"""
        return {
            BugId(raw["id"]): parse_bug(raw)
            for raw in self.raw_search(query)
            if "id" in raw
        }

    def raw_search(
        self,
        query: BugQuery = EVERYTHING,
        /,
        *,
        fields: typing.Sequence[str] = INCLUDE_FIELDS,
    ) -> tuple[RawBug, ...]:
        """Run a search, returning the wire dicts rather than :class:`Bug`.

        Use this for the narrow projections a full :class:`Bug` doesn't need;
        anything left out of ``fields`` is simply absent from the results.
        """
        base = [("include_fields", ",".join(fields))]
        overhead = len(f"{self.base_url}/rest/bug?") + len(urllib.parse.urlencode(base))
        results: list[RawBug] = []
        for batch in query.batches(base_length=overhead):
            results.extend(self._paged_search(batch, base))
        return tuple(results)

    def _paged_search(
        self, query: BugQuery, base: list[tuple[str, str]]
    ) -> typing.Iterator[RawBug]:
        offset = query.offset or 0
        limit = query.limit
        while True:
            size = min(limit, PAGE_SIZE) if limit else PAGE_SIZE
            page = query.paged(size, offset)
            payload = self._transport.request("GET", "bug", params=base + page.params())
            bugs = expect_list(payload, "bugs", "bug search")
            yield from bugs
            offset += len(bugs)
            if limit is not None:
                limit -= len(bugs)
                if limit <= 0:
                    return
            if len(bugs) < size:
                return

    def resolve_dependencies(self, bugs: dict[BugId, Bug]) -> dict[BugId, Bug]:
        """Fetch the transitive closure of everything ``bugs`` depends on.

        Dependencies that can't be fetched, because they were deleted or are
        behind a security group, are logged and dropped rather than looping.
        """
        resolved = dict(bugs)
        unreachable: set[BugId] = set()
        while True:
            missing = {
                dep
                for bug in resolved.values()
                for dep in bug.depends_on
                if dep not in resolved and dep not in unreachable
            }
            if not missing:
                return resolved
            fetched = self.search(BugQuery.ids(sorted(missing)))
            if absent := missing - fetched.keys():
                logger.warning(
                    "unreachable bug dependencies, skipping: %s", sorted(absent)
                )
                unreachable |= absent
            resolved.update(fetched)

    def comments(self, bug: BugId | int, /) -> tuple[Comment, ...]:
        """Every comment on a bug, oldest first"""
        payload = self._transport.request("GET", f"bug/{int(bug)}/comment")
        # the bugs mapping is keyed by the *stringified* bug id
        section = expect_object(payload, "comments").get("bugs", {})
        if not isinstance(section, dict) or str(bug) not in section:
            raise BugzillaSchemaError(f"comments: no entry for bug {bug}")
        return tuple(
            parse_comment(raw)
            for raw in expect_list(section[str(bug)], "comments", "comments")
        )

    def latest_comment(
        self, bug: BugId | int, /, *, creator: str | None = None
    ) -> Comment | None:
        """The newest comment, optionally restricted to one author.

        ``creator`` defaults to the authenticated account.
        """
        creator = creator if creator is not None else self.whoami().name
        for comment in reversed(self.comments(bug)):
            if comment.creator == creator:
                return comment
        return None

    def create(self, bug: NewBug, /) -> BugId:
        """File a bug and return its id.

        Never retried, since a retry after a timeout files a duplicate.
        """
        payload = self._transport.request("POST", "bug", body=bug.to_wire())
        created = expect_object(payload, "bug creation")
        if not isinstance(bug_id := created.get("id"), int):
            raise BugzillaSchemaError(f"bug creation: no id in response {created!r}")
        return BugId(bug_id)

    @typing.overload
    def update(self, bugs: BugId | int, /, update: BugUpdate) -> BugChanges: ...

    @typing.overload
    def update(
        self, bugs: typing.Iterable[BugId | int], /, update: BugUpdate
    ) -> tuple[BugChanges, ...]: ...

    def update(self, bugs: typing.Any, /, update: BugUpdate) -> typing.Any:
        """Apply an update to one or more bugs.

        The full id list always goes in the body, because Bugzilla lets the
        body override the id in the request path rather than the other way
        around.
        """
        single = isinstance(bugs, int)
        ids = [int(bugs)] if single else [int(x) for x in bugs]
        if not ids:
            raise BugzillaUsageError("update() needs at least one bug id")
        payload = self._transport.request(
            "PUT", f"bug/{ids[0]}", body=update.to_wire(ids)
        )
        changes = tuple(
            parse_changes(raw) for raw in expect_list(payload, "bugs", "bug update")
        )
        return changes[0] if single else changes

    def tag_comments(
        self, comments: typing.Iterable[CommentId | int], /, tags: ListChange[str]
    ) -> None:
        """Add or remove tags on comments, one request per comment"""
        for comment in comments:
            self._transport.request(
                "PUT", f"bug/comment/{int(comment)}/tags", body=tags.to_wire()
            )

    def mark_own_comments_obsolete(self, bug: BugId | int, /) -> int:
        """Tag the authenticated user's comments obsolete, returning the count.

        Deliberately separate from :meth:`update`, so a failed update doesn't
        leave a bug with every comment obsoleted and no replacement.
        """
        username = self.whoami().name
        stale = [
            comment.id
            for comment in self.comments(bug)
            if comment.creator == username and not comment.obsolete
        ]
        self.tag_comments(stale, ListChange.adding("obsolete"))
        return len(stale)
