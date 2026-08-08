"""Composable searches against ``GET /rest/bug``.

Constraints come in two flavours. Plain equality goes in :attr:`BugQuery.simple`
as repeated parameters, which Bugzilla ORs within a key and ANDs across keys.
Anything needing an operator becomes a :class:`Criterion` rendered into the
``f<N>``/``o<N>``/``v<N>`` boolean chart parameters, with the slot numbers
allocated at render time so any two queries can be combined.
"""

__all__ = (
    "MAX_URL_LENGTH",
    "BugQuery",
    "ChartGroup",
    "Criterion",
)

import dataclasses
import functools
import typing
import urllib.parse

from .enums import (
    UNRESOLVED,
    BugCategory,
    ChartOp,
    Component,
    FlagStatus,
    Join,
    Product,
    Status,
)
from .errors import BugzillaUsageError
from .wire import BugId

# apache's default LimitRequestLine is 8190 for the whole request line, and
# bgo's own frontend is stricter in practice
MAX_URL_LENGTH: typing.Final = 6000


@dataclasses.dataclass(frozen=True, slots=True)
class Criterion:
    """One boolean chart condition"""

    field: str
    op: ChartOp
    values: tuple[str, ...] = ()
    negate: bool = False
    splittable: bool = False

    def render(self, slot: int) -> list[tuple[str, str]]:
        params = [(f"f{slot}", self.field), (f"o{slot}", str(self.op))]
        params.extend((f"v{slot}", value) for value in self.values)
        if self.negate:
            params.append((f"n{slot}", "1"))
        return params

    def with_values(self, values: typing.Iterable[str]) -> "Criterion":
        return dataclasses.replace(self, values=tuple(values))


@dataclasses.dataclass(frozen=True, slots=True)
class ChartGroup:
    """Several conditions combined with an explicit join"""

    join: Join
    children: tuple["Criterion | ChartGroup", ...]

    def render(self, slot: int) -> tuple[list[tuple[str, str]], int]:
        params = [(f"f{slot}", "OP"), (f"j{slot}", str(self.join))]
        slot += 1
        for child in self.children:
            rendered, slot = _render(child, slot)
            params.extend(rendered)
        params.append((f"f{slot}", "CP"))
        return params, slot + 1


def _render(
    chart: Criterion | ChartGroup, slot: int
) -> tuple[list[tuple[str, str]], int]:
    if isinstance(chart, ChartGroup):
        return chart.render(slot)
    return chart.render(slot), slot + 1


# the field name, its values, and how to rebuild the query around a subset
type _SplitAxis = tuple[
    str, tuple[str, ...], typing.Callable[[typing.Sequence[str]], "BugQuery"]
]


def _merge_simple(
    left: tuple[tuple[str, tuple[str, ...]], ...],
    right: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    merged: dict[str, tuple[str, ...]] = dict(left)
    for key, values in right:
        existing = merged.get(key, ())
        merged[key] = existing + tuple(x for x in values if x not in existing)
    return tuple(merged.items())


@dataclasses.dataclass(frozen=True, slots=True)
class BugQuery:
    """A search, built from named constructors and combined with ``&``"""

    simple: tuple[tuple[str, tuple[str, ...]], ...] = ()
    charts: tuple[Criterion | ChartGroup, ...] = ()
    limit: int | None = None
    offset: int | None = None
    order: str | None = None

    @classmethod
    def ids(cls, bugs: typing.Iterable[BugId | int]) -> "BugQuery":
        return cls(simple=(("id", tuple(str(x) for x in bugs)),))

    @classmethod
    def product(cls, *products: Product | str) -> "BugQuery":
        return cls(simple=(("product", tuple(str(x) for x in products)),))

    @classmethod
    def component(cls, *components: Component | str) -> "BugQuery":
        return cls(simple=(("component", tuple(str(x) for x in components)),))

    @classmethod
    def category(cls, *categories: BugCategory) -> "BugQuery":
        """Restrict to keywordreqs and/or stablereqs"""
        return cls(
            simple=(
                ("product", (str(Product.GENTOO_LINUX),)),
                ("component", tuple(str(x.component) for x in categories)),
            )
        )

    @classmethod
    def unresolved(cls) -> "BugQuery":
        """Match open bugs, i.e. those with no resolution set.

        Selecting on the open statuses instead returns the same set, since
        Bugzilla only leaves the resolution empty while the status is open, so
        this is the one spelling worth having.
        """
        return cls(simple=(("resolution", (UNRESOLVED,)),))

    @classmethod
    def resolution(cls, *resolutions: str) -> "BugQuery":
        return cls(simple=(("resolution", tuple(map(str, resolutions))),))

    @classmethod
    def status(cls, *statuses: Status | str) -> "BugQuery":
        return cls(simple=(("bug_status", tuple(map(str, statuses))),))

    @classmethod
    def cc(cls, *emails: str) -> "BugQuery":
        return cls(simple=(("cc", tuple(emails)),))

    @classmethod
    def assigned_to(cls, *emails: str) -> "BugQuery":
        return cls(simple=(("assigned_to", tuple(emails)),))

    @classmethod
    def keywords(cls, *keywords: str) -> "BugQuery":
        return cls(charts=(Criterion("keywords", ChartOp.ANY_WORDS, tuple(keywords)),))

    @classmethod
    def flag(cls, name: str, *statuses: FlagStatus | str) -> "BugQuery":
        """Match a flag by status.

        Bugzilla can't express "flag is absent"; those bugs have to be fetched
        and filtered client side.
        """
        return cls(
            charts=(
                Criterion(
                    "flagtypes.name",
                    ChartOp.ANY_WORDS,
                    tuple(f"{name}{status}" for status in statuses),
                ),
            )
        )

    @classmethod
    def without_tags(cls, *tags: str) -> "BugQuery":
        """Exclude bugs carrying any of these personal tags"""
        return cls(charts=(Criterion("tag", ChartOp.NO_WORDS_SUBSTR, tuple(tags)),))

    @classmethod
    def package_list_any(cls, packages: typing.Iterable[object]) -> "BugQuery":
        """Match bugs whose package list mentions any of these packages"""
        return cls(
            charts=(
                Criterion(
                    "cf_stabilisation_atoms",
                    ChartOp.ANY_WORDS,
                    tuple(str(x) for x in packages),
                    splittable=True,
                ),
            )
        )

    @classmethod
    def any_of(cls, *queries: "BugQuery") -> "BugQuery":
        """OR several chart-only queries together.

        Simple parameters can't take part in a chart group, so a query holding
        any is rejected rather than silently ANDed in.
        """
        charts: list[Criterion | ChartGroup] = []
        for query in queries:
            if query.simple:
                raise BugzillaUsageError(
                    "any_of() only accepts chart based queries, got "
                    f"{[key for key, _ in query.simple]}"
                )
            charts.extend(query.charts)
        return cls(charts=(ChartGroup(Join.OR, tuple(charts)),))

    def __and__(self, other: "BugQuery") -> "BugQuery":
        return BugQuery(
            simple=_merge_simple(self.simple, other.simple),
            charts=self.charts + other.charts,
            limit=self.limit if other.limit is None else other.limit,
            offset=self.offset if other.offset is None else other.offset,
            order=other.order or self.order,
        )

    def paged(self, limit: int, offset: int = 0) -> "BugQuery":
        """Return a copy with explicit paging.

        Bugzilla rejects an offset without a limit, and treats ``limit=0`` as
        unlimited while silently discarding the offset, so both are refused.
        """
        if limit <= 0:
            raise BugzillaUsageError(f"limit must be positive, got {limit}")
        if offset < 0:
            raise BugzillaUsageError(f"offset must not be negative, got {offset}")
        return dataclasses.replace(self, limit=limit, offset=offset)

    def params(self) -> list[tuple[str, str]]:
        """Render to ordered query parameters.

        Ordered pairs rather than a mapping, since chart slots are positional
        and duplicate keys are meaningful.
        """
        params: list[tuple[str, str]] = []
        for key, values in self.simple:
            params.extend((key, value) for value in values)
        slot = 1
        for chart in self.charts:
            rendered, slot = _render(chart, slot)
            params.extend(rendered)
        if self.limit is not None:
            params.append(("limit", str(self.limit)))
        if self.offset:
            params.append(("offset", str(self.offset)))
        if self.order is not None:
            params.append(("order", self.order))
        return params

    def batches(
        self, base_length: int = 0, max_length: int = MAX_URL_LENGTH
    ) -> typing.Iterator["BugQuery"]:
        """Split into sub-queries whose encoded parameters each fit the budget.

        Only the largest splittable axis is divided, either the ``id`` simple
        parameter or a :class:`Criterion` marked splittable; everything else is
        repeated in every batch. Sizing uses the encoded length rather than a
        count, so it adapts to long atoms instead of guessing.
        """
        if (axis := self._split_axis()) is None:
            yield self
            return
        key, values, rebuild = axis
        empty = rebuild(())
        budget = max_length - base_length - len(urllib.parse.urlencode(empty.params()))
        batch: list[str] = []
        used = 0
        for value in values:
            cost = len(urllib.parse.urlencode(((key, value),))) + 1
            if batch and used + cost > budget:
                yield rebuild(batch)
                batch, used = [], 0
            batch.append(value)
            used += cost
        yield rebuild(batch)

    def _split_axis(self) -> "_SplitAxis | None":
        """Pick the widest axis to spread across batches, if there is one"""
        candidates: list[_SplitAxis] = [
            (key, values, functools.partial(self._rebuild_simple, key))
            for key, values in self.simple
            if key == "id"
        ]
        candidates.extend(
            (chart.field, chart.values, functools.partial(self._rebuild_chart, index))
            for index, chart in enumerate(self.charts)
            if isinstance(chart, Criterion) and chart.splittable
        )
        if not candidates:
            return None
        return max(candidates, key=lambda axis: len("".join(axis[1])))

    def _rebuild_simple(self, key: str, values: typing.Sequence[str]) -> "BugQuery":
        simple = tuple(x for x in self.simple if x[0] != key)
        if values:
            simple += ((key, tuple(values)),)
        return dataclasses.replace(self, simple=simple)

    def _rebuild_chart(self, index: int, values: typing.Sequence[str]) -> "BugQuery":
        charts = list(self.charts)
        charts[index] = typing.cast(Criterion, charts[index]).with_values(values)
        return dataclasses.replace(self, charts=tuple(charts))
