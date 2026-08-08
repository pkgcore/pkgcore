"""Bugzilla vocabularies used by bugs.gentoo.org.

Only what pkgcore-adjacent tooling actually writes is enumerated; values read
back off the wire stay plain strings, so anything Gentoo adds later never
breaks parsing.
"""

__all__ = (
    "OPEN_STATUSES",
    "UNRESOLVED",
    "BugCategory",
    "ChartOp",
    "Component",
    "FlagStatus",
    "Join",
    "Product",
    "Resolution",
    "RuntimeTesting",
    "Severity",
    "Status",
)

import enum
import typing


class Product(enum.StrEnum):
    """The bugs.gentoo.org products this module knows about"""

    GENTOO_LINUX = "Gentoo Linux"
    GENTOO_SECURITY = "Gentoo Security"


class Component(enum.StrEnum):
    """Components of Gentoo Linux, plus the security one that matters"""

    STABILIZATION = "Stabilization"
    KEYWORDING = "Keywording"
    CURRENT_PACKAGES = "Current packages"
    NEW_PACKAGES = "New packages"
    ECLASSES = "Eclasses"
    PROFILES = "Profiles"
    VULNERABILITIES = "Vulnerabilities"


class Status(enum.StrEnum):
    """Bug workflow states, there is no NEW, ASSIGNED or CLOSED"""

    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"

    @property
    def is_open(self) -> bool:
        return self in OPEN_STATUSES


OPEN_STATUSES: typing.Final[tuple["Status", ...]] = (
    Status.UNCONFIRMED,
    Status.CONFIRMED,
    Status.IN_PROGRESS,
)

# selects unresolved bugs in a search; an open bug stores the empty string
UNRESOLVED: typing.Final = "---"


class Resolution(enum.StrEnum):
    """Resolutions enabled on bugs.gentoo.org.

    LATER and REMIND are legacy values still set on old bugs, listed so parsing
    round-trips rather than because anything should write them.
    """

    FIXED = "FIXED"
    INVALID = "INVALID"
    WONTFIX = "WONTFIX"
    LATER = "LATER"
    REMIND = "REMIND"
    DUPLICATE = "DUPLICATE"
    WORKSFORME = "WORKSFORME"
    CANTFIX = "CANTFIX"
    NEEDINFO = "NEEDINFO"
    TEST_REQUEST = "TEST-REQUEST"
    UPSTREAM = "UPSTREAM"
    OBSOLETE = "OBSOLETE"
    PKGREMOVED = "PKGREMOVED"


class Severity(enum.StrEnum):
    """Bug severities, QA being Gentoo specific"""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    NORMAL = "normal"
    MINOR = "minor"
    TRIVIAL = "trivial"
    ENHANCEMENT = "enhancement"
    QA = "QA"


class FlagStatus(enum.StrEnum):
    """Status of a Bugzilla flag, CLEARED being write only"""

    REQUESTED = "?"
    GRANTED = "+"
    DENIED = "-"
    CLEARED = "X"


class RuntimeTesting(enum.StrEnum):
    """Values of cf_runtime_testing_required.

    The field only exists on the Keywording and Stabilization components, and
    reads back as UNSET everywhere else.
    """

    UNSET = "---"
    YES = "Yes"
    NO = "No"
    MANUAL = "Manual"


class BugCategory(enum.StrEnum):
    """Gentoo arch team bug categories, valued by their Bugzilla component"""

    KEYWORDREQ = "Keywording"
    STABLEREQ = "Stabilization"

    @classmethod
    def from_product_component(
        cls, product: str, component: str
    ) -> "BugCategory | None":
        """Classify a bug, returning None if it's neither category"""
        if product == Product.GENTOO_LINUX:
            try:
                return cls(component)
            except ValueError:
                pass
        return None

    @property
    def product(self) -> Product:
        return Product.GENTOO_LINUX

    @property
    def component(self) -> Component:
        return Component(self.value)

    @property
    def summary_suffix(self) -> str:
        """The conventional trailing word of the bug summary"""
        return "keywordreq" if self is BugCategory.KEYWORDREQ else "stablereq"

    @property
    def verb(self) -> str:
        """The verb used when describing the request"""
        return "keyword" if self is BugCategory.KEYWORDREQ else "stabilize"


class ChartOp(enum.StrEnum):
    """Operators accepted by Bugzilla's boolean charts, the o<N> params.

    MATCHES and NOT_MATCHES are only valid against the fulltext content field,
    and IS_EMPTY/IS_NOT_EMPTY still need a v<N> value even though it's ignored.
    """

    EQUALS = "equals"
    NOT_EQUALS = "notequals"
    CASE_SUBSTRING = "casesubstring"
    SUBSTRING = "substring"
    NOT_SUBSTRING = "notsubstring"
    REGEXP = "regexp"
    NOT_REGEXP = "notregexp"
    LESS_THAN = "lessthan"
    LESS_THAN_EQ = "lessthaneq"
    GREATER_THAN = "greaterthan"
    GREATER_THAN_EQ = "greaterthaneq"
    MATCHES = "matches"
    NOT_MATCHES = "notmatches"
    ANY_EXACT = "anyexact"
    ANY_WORDS_SUBSTR = "anywordssubstr"
    ALL_WORDS_SUBSTR = "allwordssubstr"
    NO_WORDS_SUBSTR = "nowordssubstr"
    ANY_WORDS = "anywords"
    ALL_WORDS = "allwords"
    NO_WORDS = "nowords"
    CHANGED_BEFORE = "changedbefore"
    CHANGED_AFTER = "changedafter"
    CHANGED_FROM = "changedfrom"
    CHANGED_TO = "changedto"
    CHANGED_BY = "changedby"
    IS_EMPTY = "isempty"
    IS_NOT_EMPTY = "isnotempty"


class Join(enum.StrEnum):
    """How a boolean chart group combines its children, the j<N> params.

    AND_G requires every condition to match the same row, which is what
    constraining a single flag or attachment needs.
    """

    AND = "AND"
    OR = "OR"
    AND_G = "AND_G"
