"""Typed client for the bugs.gentoo.org Bugzilla REST API.

The public surface is re-exported here; the implementation is split across
submodules so that :mod:`pkgcore.bugzilla.wire` and friends can be imported
without dragging in the HTTP transport.

    >>> from pkgcore.bugzilla import Bugzilla, BugQuery, Component, FlagStatus
    >>> bz = Bugzilla()                                   # doctest: +SKIP
    >>> query = (BugQuery.component(Component.STABILIZATION)
    ...          & BugQuery.unresolved()
    ...          & BugQuery.flag("sanity-check", FlagStatus.GRANTED))
    >>> bugs = bz.search(query)                           # doctest: +SKIP
"""

__all__ = (
    "INCLUDE_FIELDS",
    "AuthMode",
    "Bug",
    "BugCategory",
    "BugChanges",
    "BugQuery",
    "BugUpdate",
    "Bugzilla",
    "BugzillaError",
    "Comment",
    "Component",
    "Criterion",
    "Flag",
    "FlagChange",
    "FlagStatus",
    "ListChange",
    "NewBug",
    "NewComment",
    "PackageList",
    "PackageListEntry",
    "PackageListError",
    "Product",
    "Resolution",
    "RuntimeTesting",
    "Severity",
    "Status",
    "User",
)

from .bug import INCLUDE_FIELDS, Bug, BugChanges, Comment, Flag, User
from .changes import BugUpdate, FlagChange, ListChange, NewBug, NewComment
from .client import Bugzilla
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
from .errors import BugzillaError, PackageListError
from .pkglist import PackageList, PackageListEntry
from .query import BugQuery, Criterion
from .transport import AuthMode
