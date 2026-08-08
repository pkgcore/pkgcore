"""Replay helpers for testing code that talks to Bugzilla.

Subclassing the real urllib handler rather than patching ``urlopen`` keeps the
genuine :class:`urllib.request.Request` in the loop, so header, method, body
and encoding mistakes are caught, and an unexpected request fails loudly
instead of reaching the network.

Nothing here imports pytest, so it is usable from a plain ``unittest`` suite or
a script; :mod:`pkgcore.pytest.plugin` wraps it in a ``bugzilla_cassette`` fixture that
downstream projects get for free.

A cassette used as a context manager takes over the opener every client builds,
which is what lets it intercept a client constructed somewhere the test can't
reach, such as inside a CLI command::

    with Cassette().expect_created(12345) as cassette:
        main(["pkgdev", "bugs", "..."])
    assert cassette.calls[0].body["summary"] == "cat/pkg-1: stablereq"

When the client is reachable, skip the patching and hand it the opener::

    cassette = Cassette().expect_bugs({"id": 1, ...})
    bugs = cassette.client().search()
"""

__all__ = ("Call", "Cassette", "Recording", "ReplayHandler", "response")

import contextlib
import dataclasses
import email.message
import io
import itertools
import json
import types
import typing
import urllib.parse
import urllib.request
import urllib.response

from . import transport
from .client import Bugzilla

API_KEY: typing.Final = "fake-api-key-for-tests"
BASE_URL: typing.Final = "https://bugs.example.org"

type _Body = typing.Any | typing.Callable[["Call"], typing.Any]


@dataclasses.dataclass(frozen=True, slots=True)
class Call:
    """A request the code under test actually made"""

    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, typing.Any] | None

    @property
    def path(self) -> str:
        return urllib.parse.urlsplit(self.url).path

    @property
    def query(self) -> list[tuple[str, str]]:
        """Query parameters in order, duplicates preserved"""
        return urllib.parse.parse_qsl(
            urllib.parse.urlsplit(self.url).query, keep_blank_values=True
        )

    @property
    def params(self) -> dict[str, list[str]]:
        """Query parameters grouped by name"""
        grouped: dict[str, list[str]] = {}
        for key, value in self.query:
            grouped.setdefault(key, []).append(value)
        return grouped

    def header(self, name: str) -> str | None:
        """Look a header up without caring how urllib cased it"""
        lowered = name.lower()
        return next((v for k, v in self.headers.items() if k.lower() == lowered), None)


@dataclasses.dataclass(frozen=True, slots=True)
class Recording:
    """A canned response.

    ``body`` is serialized to JSON, or may be a callable taking the
    :class:`Call` for responses that vary per request. ``raw`` overrides it
    with exact bytes, for testing non-JSON replies.
    """

    body: _Body = None
    status: int = 200
    raw: bytes | None = None
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    content_type: str = "application/json; charset=UTF-8"
    reason: str = "OK"

    def payload(self, call: Call) -> bytes:
        if self.raw is not None:
            return self.raw
        body = self.body(call) if callable(self.body) else self.body
        return json.dumps(body).encode()


def response(body: _Body = None, **kwargs: typing.Any) -> Recording:
    """Shorthand for :class:`Recording`"""
    return Recording(body, **kwargs)


class ReplayHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    """Serve queued recordings in order, recording what was asked for.

    Subclasses both handlers so :func:`urllib.request.build_opener` drops its
    defaults for either scheme; inheriting only the https one leaves plain http
    going to the network.
    """

    def __init__(self, cassette: "Cassette") -> None:
        super().__init__()
        self.cassette = cassette

    def https_open(self, req: typing.Any) -> typing.Any:
        call = Call(
            req.get_method(),
            req.full_url,
            dict(req.headers),
            json.loads(req.data.decode()) if req.data else None,
        )
        recording = self.cassette._consume(call)

        headers = email.message.Message()
        headers["Content-Type"] = recording.content_type
        for key, value in recording.headers.items():
            headers[key] = value
        result = urllib.response.addinfourl(
            io.BytesIO(recording.payload(call)),
            headers,
            req.full_url,
            recording.status,
        )
        # HTTPErrorProcessor reads .msg when turning a 4xx/5xx into an error
        result.msg = recording.reason  # type: ignore[attr-defined]
        return result

    http_open = https_open


class Cassette:
    """Queued responses, the requests they answered, and a client to drive.

    Recordings queued with :meth:`expect` are consumed in order; once they run
    out an :meth:`always` fallback answers, or an unexpected request fails.
    """

    def __init__(
        self,
        *recordings: Recording,
        api_key: str | None = API_KEY,
        base_url: str = BASE_URL,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.calls: list[Call] = []
        self.pending: list[Recording] = list(recordings)
        self.fallback: Recording | None = None
        self.opener = urllib.request.build_opener(ReplayHandler(self))

    def _consume(self, call: Call) -> Recording:
        self.calls.append(call)
        if self.pending:
            return self.pending.pop(0)
        if self.fallback is not None:
            return self.fallback
        raise AssertionError(f"unexpected request: {call.method} {call.url}")

    def expect(self, *recordings: Recording) -> "Cassette":
        """Queue responses, returning self so calls can be chained"""
        self.pending.extend(recordings)
        return self

    def always(self, recording: Recording) -> "Cassette":
        """Answer any request the queue doesn't cover"""
        self.fallback = recording
        return self

    def expect_bugs(self, *bugs: dict[str, typing.Any]) -> "Cassette":
        """Queue a search result"""
        return self.expect(response({"bugs": list(bugs)}))

    def expect_created(self, *bug_ids: int) -> "Cassette":
        """Queue replies to bug creation"""
        return self.expect(*(response({"id": bug_id}) for bug_id in bug_ids))

    def creates_bugs(self, first: int = 1) -> "Cassette":
        """Answer every creation with the next id, for unbounded filing"""
        counter = itertools.count(first)
        return self.always(response(lambda call: {"id": next(counter)}))

    def expect_changed(self, bug_id: int, **changes: dict[str, str]) -> "Cassette":
        """Queue a reply to an update"""
        return self.expect(
            response(
                {
                    "bugs": [
                        {
                            "id": bug_id,
                            "alias": [],
                            "last_change_time": "2024-01-02T03:04:05Z",
                            "changes": changes,
                        }
                    ]
                }
            )
        )

    def expect_error(
        self, code: int, message: str = "error", status: int = 400
    ) -> "Cassette":
        """Queue a Bugzilla error body"""
        return self.expect(
            response({"error": True, "code": code, "message": message}, status=status)
        )

    def expect_whoami(
        self, name: str = "dev@gentoo.org", real_name: str = "A Dev", id: int = 7
    ) -> "Cassette":
        return self.expect(response({"id": id, "name": name, "real_name": real_name}))

    def transport(self, **kwargs: typing.Any) -> transport.UrllibTransport:
        """A transport wired to this cassette"""
        kwargs.setdefault("api_key", self.api_key)
        kwargs.setdefault("retries", 1)
        return transport.UrllibTransport(self.base_url, opener=self.opener, **kwargs)

    def client(self, **kwargs: typing.Any) -> Bugzilla:
        """A client wired to this cassette"""
        kwargs.setdefault("api_key", self.api_key)
        kwargs.setdefault("retries", 1)
        api_key = kwargs.pop("api_key")
        return Bugzilla(api_key, base_url=self.base_url, opener=self.opener, **kwargs)

    @contextlib.contextmanager
    def installed(self) -> typing.Generator[typing.Self, None, None]:
        """Make every client built while active use this cassette"""
        original = transport.build_opener
        transport.build_opener = lambda: self.opener
        try:
            yield self
        finally:
            transport.build_opener = original

    def __enter__(self) -> typing.Self:
        self._installed = self.installed()
        return self._installed.__enter__()

    def __exit__(
        self,
        kls: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self._installed.__exit__(kls, exc, traceback)

    def assert_drained(self) -> None:
        """Fail if queued responses went unused"""
        if self.pending:
            raise AssertionError(
                f"{len(self.pending)} unused recordings after "
                f"{len(self.calls)} requests"
            )
