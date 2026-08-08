"""Exceptions raised by pkgcore.bugzilla.

Bugzilla reports failures as a JSON body {"error": true, "code": N, "message":
...}, and derives the HTTP status from the code through a lossy table. Dispatch
on the code, not the status: an invalid api key is code 306 delivered as HTTP
400, permission denied is code 102 delivered as HTTP 401, and bugs.gentoo.org
never emits 403 at all.
"""

__all__ = (
    "BugzillaAuthError",
    "BugzillaAuthRequired",
    "BugzillaConnectionError",
    "BugzillaError",
    "BugzillaInvalidField",
    "BugzillaNotFound",
    "BugzillaPermissionDenied",
    "BugzillaProtocolError",
    "BugzillaResponseError",
    "BugzillaSchemaError",
    "BugzillaServerError",
    "BugzillaUsageError",
    "PackageListError",
    "from_response",
    "from_status",
)

import typing

from ..exceptions import PkgcoreUserException


class BugzillaError(PkgcoreUserException):
    """Base for every failure raised by pkgcore.bugzilla"""


class BugzillaUsageError(BugzillaError, ValueError):
    """The request couldn't be built, raised locally without any network use"""


class BugzillaConnectionError(BugzillaError):
    """DNS, TCP, TLS or timeout failure, after any retries were exhausted"""


class BugzillaProtocolError(BugzillaError):
    """The server answered with something that isn't a Bugzilla REST reply"""


class BugzillaSchemaError(BugzillaProtocolError):
    """Valid JSON, but not the shape the endpoint documents"""


class BugzillaResponseError(BugzillaError):
    """Bugzilla returned an error body"""

    def __init__(
        self, message: str, *, code: int = 0, status: int = 0, url: str = ""
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.url = url

    def __str__(self) -> str:
        details = ", ".join(
            f"{name}={value}"
            for name, value in (("code", self.code), ("http", self.status))
            if value
        )
        return f"{self.message} [{details}]" if details else self.message


class BugzillaAuthError(BugzillaResponseError):
    """Authentication failed, or the request requires being logged in"""


class BugzillaAuthRequired(BugzillaAuthError):
    """A write was attempted without an api key, raised without a round trip"""


class BugzillaNotFound(BugzillaResponseError):
    """The requested bug, comment or REST route doesn't exist"""


class BugzillaPermissionDenied(BugzillaResponseError):
    """The account is known but isn't allowed to see or change this"""


class BugzillaInvalidField(BugzillaResponseError):
    """A field name or value was rejected"""


class BugzillaServerError(BugzillaResponseError):
    """A 5xx from the web tier in front of Bugzilla"""

    def __init__(
        self, message: str, *, retry_after: float | None = None, **kwargs: typing.Any
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class PackageListError(BugzillaError):
    """Malformed cf_stabilisation_atoms content"""

    def __init__(
        self,
        message: str,
        *,
        bug_id: int | None = None,
        lineno: int | None = None,
        line: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.bug_id = bug_id
        self.lineno = lineno
        self.line = line

    def __str__(self) -> str:
        where = ""
        if self.bug_id is not None:
            where += f"bug {self.bug_id}"
        if self.lineno is not None:
            where += f"{', ' if where else ''}line {self.lineno}"
        return f"{where}: {self.message}" if where else self.message


# codes per Bugzilla/WebService/Constants.pm, limited to what bgo emits
_CODE_MAP: typing.Final[dict[int, type[BugzillaResponseError]]] = {
    **dict.fromkeys(
        (50, 53, 100, 104, 108, 111, 114, 115, *range(129, 135), *range(1101, 1106)),
        BugzillaInvalidField,
    ),
    **dict.fromkeys((51, 101, 32614), BugzillaNotFound),
    **dict.fromkeys((102, 106, 109, 110, 113, 120), BugzillaPermissionDenied),
    **dict.fromkeys((*range(300, 308), 410, 504), BugzillaAuthError),
}


def from_response(
    error: typing.Mapping[str, typing.Any],
    status: int,
    url: str,
    retry_after: float | None = None,
) -> BugzillaResponseError:
    """Build the most specific exception for a Bugzilla error body"""
    code = error.get("code")
    code = code if isinstance(code, int) else 0
    message = str(error.get("message") or "unknown Bugzilla error")
    if (kls := _CODE_MAP.get(code)) is None:
        kls = BugzillaServerError if status >= 500 else BugzillaResponseError
    if kls is BugzillaServerError:
        return BugzillaServerError(
            message, code=code, status=status, url=url, retry_after=retry_after
        )
    return kls(message, code=code, status=status, url=url)


def from_status(
    status: int, url: str, payload: bytes = b"", retry_after: float | None = None
) -> BugzillaResponseError:
    """Build an exception for a failing response that carried no error body"""
    message = f"HTTP {status} from {url}"
    if snippet := payload[:200].decode("utf-8", "replace").strip():
        message = f"{message}: {snippet}"
    if status >= 500:
        return BugzillaServerError(
            message, status=status, url=url, retry_after=retry_after
        )
    if status in (401, 403):
        return BugzillaAuthError(message, status=status, url=url)
    if status == 404:
        return BugzillaNotFound(message, status=status, url=url)
    return BugzillaResponseError(message, status=status, url=url)
