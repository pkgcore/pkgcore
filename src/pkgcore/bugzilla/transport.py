"""HTTP plumbing for the Bugzilla REST API, on top of stdlib urllib."""

__all__ = (
    "USER_AGENT",
    "AuthMode",
    "Transport",
    "UrllibTransport",
    "build_opener",
    "build_user_agent",
    "expect_list",
    "expect_object",
    "redact",
)

import enum
import http.client
import json
import random
import time
import typing
import urllib.error
import urllib.parse
import urllib.request

from .. import __version__
from ..log import logger
from . import errors
from .wire import JSONValue, RequestBody

USER_AGENT: typing.Final = f"pkgcore/{__version__}"


def build_user_agent(client: str | None = None) -> str:
    """Compose the User-Agent, most specific product first.

    A caller's own token goes in front of pkgcore's rather than replacing it,
    so Gentoo infra can tell which tool the traffic came from while pkgcore
    stays identifiable.
    """
    return f"{client} {USER_AGENT}" if client else USER_AGENT


_RETRY_STATUSES: typing.Final = frozenset((429, 500, 502, 503, 504))
_IDEMPOTENT: typing.Final = frozenset(("GET", "HEAD"))
_API_KEY_PARAM: typing.Final = "Bugzilla_api_key"


class AuthMode(enum.StrEnum):
    """Where the api key is placed.

    ``QUERY`` is the only mode bugs.gentoo.org honours today; ``HEADER`` exists
    for instances running Bugzilla 6.
    """

    QUERY = "query"
    HEADER = "header"


class Transport(typing.Protocol):
    """The seam a client talks through"""

    def request(
        self,
        method: str,
        path: str,
        *,
        params: typing.Sequence[tuple[str, str]] = (),
        body: RequestBody | None = None,
    ) -> JSONValue: ...


def redact(url: str) -> str:
    """Strip the api key out of a url before it reaches a log or traceback"""
    split = urllib.parse.urlsplit(url)
    if not split.query:
        return url
    query = [
        (key, "<redacted>" if key == _API_KEY_PARAM else value)
        for key, value in urllib.parse.parse_qsl(split.query, keep_blank_values=True)
    ]
    return urllib.parse.urlunsplit(split._replace(query=urllib.parse.urlencode(query)))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects, which would leak the key to another host"""

    def redirect_request(self, req: typing.Any, *args: typing.Any) -> None:
        return None


def build_opener() -> urllib.request.OpenerDirector:
    """The opener used when a transport isn't given one.

    Indirected through a function so that :mod:`pkgcore.bugzilla.testing` can
    replace it, and intercept clients built somewhere it can't reach.
    """
    return urllib.request.build_opener(_NoRedirect())


class UrllibTransport:
    """A Bugzilla transport built on :mod:`urllib.request`.

    Reads are retried with exponential backoff, since bugs.gentoo.org signals
    overload by resetting the connection rather than returning 429. Writes are
    not, because a retried bug creation files a duplicate.
    """

    __slots__ = (
        "_api_key",
        "_auth_mode",
        "_base_url",
        "_opener",
        "_retries",
        "_retry_writes",
        "_timeout",
        "_user_agent",
    )

    def __init__(
        self,
        base_url: str = "https://bugs.gentoo.org",
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        retries: int = 3,
        auth_mode: AuthMode = AuthMode.QUERY,
        retry_writes: bool = False,
        user_agent: str | None = None,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = build_user_agent(user_agent)
        self._api_key = api_key
        self._timeout = timeout
        self._retries = max(1, retries)
        self._auth_mode = auth_mode
        self._retry_writes = retry_writes
        self._opener = opener or build_opener()

    @property
    def authenticated(self) -> bool:
        return self._api_key is not None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: typing.Sequence[tuple[str, str]] = (),
        body: RequestBody | None = None,
    ) -> JSONValue:
        if method not in _IDEMPOTENT and self._api_key is None:
            raise errors.BugzillaAuthRequired(
                f"{method} {path} needs an api key, this client is anonymous"
            )
        attempts = self._retries if method in _IDEMPOTENT or self._retry_writes else 1
        for attempt in range(attempts):
            try:
                return self._attempt(method, path, params, body)
            except (errors.BugzillaServerError, errors.BugzillaConnectionError) as exc:
                if attempt + 1 >= attempts:
                    raise
                delay = getattr(exc, "retry_after", None)
                if delay is None:
                    delay = (2**attempt) * 0.5 * (1.0 + random.random())
                logger.debug("retrying %s %s in %.1fs: %s", method, path, delay, exc)
                time.sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    def _attempt(
        self,
        method: str,
        path: str,
        params: typing.Sequence[tuple[str, str]],
        body: RequestBody | None,
    ) -> JSONValue:
        query = list(params)
        headers = {"Accept": "application/json", "User-Agent": self._user_agent}
        if self._api_key is not None:
            if self._auth_mode is AuthMode.HEADER:
                headers["X-BUGZILLA-API-KEY"] = self._api_key
            elif body is not None:
                body = {_API_KEY_PARAM: self._api_key, **body}
            else:
                query.append((_API_KEY_PARAM, self._api_key))

        url = f"{self._base_url}/rest/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload, status = response.read(), response.status
                retry_after = response.headers.get("Retry-After")
        except urllib.error.HTTPError as exc:
            payload, status, retry_after = (
                exc.read(),
                exc.code,
                exc.headers.get("Retry-After"),
            )
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException) as exc:
            reason = getattr(exc, "reason", exc)
            raise errors.BugzillaConnectionError(
                f"{method} {redact(url)}: {reason}"
            ) from exc
        return _decode(method, redact(url), status, payload, _retry_after(retry_after))


def _retry_after(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _decode(
    method: str,
    url: str,
    status: int,
    payload: bytes,
    retry_after: float | None,
) -> JSONValue:
    """Turn a response into JSON, or the most specific exception available"""
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if status in _RETRY_STATUSES:
            raise errors.BugzillaServerError(
                f"{method} {url}: HTTP {status}", status=status, retry_after=retry_after
            ) from exc
        raise errors.BugzillaProtocolError(
            f"{method} {url}: HTTP {status}, response isn't JSON: {payload[:200]!r}"
        ) from exc

    # bugzilla reports some failures with a 2xx status, so the body wins
    if isinstance(decoded, dict) and decoded.get("error"):
        raise errors.from_response(decoded, status, url, retry_after)
    if status >= 400:
        raise errors.from_status(status, url, payload, retry_after)
    return typing.cast(JSONValue, decoded)


def expect_object(payload: JSONValue, context: str) -> dict[str, typing.Any]:
    if not isinstance(payload, dict):
        raise errors.BugzillaSchemaError(
            f"{context}: expected an object, got {type(payload).__name__}"
        )
    return payload


def expect_list(payload: JSONValue, key: str, context: str) -> list[typing.Any]:
    value = expect_object(payload, context).get(key)
    if not isinstance(value, list):
        raise errors.BugzillaSchemaError(
            f"{context}: expected a {key!r} list, got {type(value).__name__}"
        )
    return value
