import urllib.parse

import pytest

from pkgcore.bugzilla.enums import (
    BugCategory,
    ChartOp,
    Component,
    FlagStatus,
    Join,
    Product,
    Status,
)
from pkgcore.bugzilla.errors import BugzillaUsageError
from pkgcore.bugzilla.query import MAX_URL_LENGTH, BugQuery, ChartGroup, Criterion


def encoded(query):
    return urllib.parse.urlencode(query.params())


class TestSimpleParams:
    def test_empty(self):
        assert BugQuery().params() == []

    def test_ids(self):
        assert BugQuery.ids((1, 2, 3)).params() == [
            ("id", "1"),
            ("id", "2"),
            ("id", "3"),
        ]

    def test_component(self):
        query = BugQuery.component(Component.STABILIZATION, Component.KEYWORDING)
        assert query.params() == [
            ("component", "Stabilization"),
            ("component", "Keywording"),
        ]

    def test_category(self):
        query = BugQuery.category(BugCategory.STABLEREQ, BugCategory.KEYWORDREQ)
        assert query.params() == [
            ("product", "Gentoo Linux"),
            ("component", "Stabilization"),
            ("component", "Keywording"),
        ]

    def test_unresolved(self):
        assert BugQuery.unresolved().params() == [("resolution", "---")]

    def test_status(self):
        query = BugQuery.status(Status.CONFIRMED, Status.IN_PROGRESS)
        assert query.params() == [
            ("bug_status", "CONFIRMED"),
            ("bug_status", "IN_PROGRESS"),
        ]

    def test_cc_and_assigned_to(self):
        query = BugQuery.cc("amd64@gentoo.org") & BugQuery.assigned_to("m@gentoo.org")
        assert query.params() == [
            ("cc", "amd64@gentoo.org"),
            ("assigned_to", "m@gentoo.org"),
        ]

    def test_product(self):
        assert BugQuery.product(Product.GENTOO_SECURITY).params() == [
            ("product", "Gentoo Security")
        ]


class TestCharts:
    def test_flag(self):
        query = BugQuery.flag("sanity-check", FlagStatus.GRANTED, FlagStatus.DENIED)
        assert query.params() == [
            ("f1", "flagtypes.name"),
            ("o1", "anywords"),
            ("v1", "sanity-check+"),
            ("v1", "sanity-check-"),
        ]

    def test_without_tags(self):
        assert BugQuery.without_tags("nattka:skip").params() == [
            ("f1", "tag"),
            ("o1", "nowordssubstr"),
            ("v1", "nattka:skip"),
        ]

    def test_negate(self):
        query = BugQuery(
            charts=(Criterion("keywords", ChartOp.ANY_WORDS, ("x",), negate=True),)
        )
        assert query.params() == [
            ("f1", "keywords"),
            ("o1", "anywords"),
            ("v1", "x"),
            ("n1", "1"),
        ]

    def test_slots_are_allocated_at_render_time(self):
        query = (
            BugQuery.flag("sanity-check", FlagStatus.GRANTED)
            & BugQuery.without_tags("nattka:skip")
            & BugQuery.keywords("ALLARCHES")
        )
        slots = [key for key, _ in query.params() if key.startswith("f")]
        assert slots == ["f1", "f2", "f3"]

    def test_combining_never_collides(self):
        # each half is authored as f1; combining must renumber
        combined = BugQuery.flag("sanity-check", FlagStatus.GRANTED) & BugQuery.flag(
            "other", FlagStatus.DENIED
        )
        assert combined.params() == [
            ("f1", "flagtypes.name"),
            ("o1", "anywords"),
            ("v1", "sanity-check+"),
            ("f2", "flagtypes.name"),
            ("o2", "anywords"),
            ("v2", "other-"),
        ]

    def test_any_of(self):
        query = BugQuery.any_of(
            BugQuery.keywords("ALLARCHES"),
            BugQuery.flag("sanity-check", FlagStatus.DENIED),
        )
        assert query.params() == [
            ("f1", "OP"),
            ("j1", "OR"),
            ("f2", "keywords"),
            ("o2", "anywords"),
            ("v2", "ALLARCHES"),
            ("f3", "flagtypes.name"),
            ("o3", "anywords"),
            ("v3", "sanity-check-"),
            ("f4", "CP"),
        ]

    def test_any_of_rejects_simple_params(self):
        with pytest.raises(BugzillaUsageError, match="chart based"):
            BugQuery.any_of(BugQuery.unresolved(), BugQuery.keywords("x"))

    def test_nested_groups(self):
        inner = ChartGroup(Join.AND, (Criterion("a", ChartOp.EQUALS, ("1",)),))
        query = BugQuery(charts=(ChartGroup(Join.OR, (inner,)),))
        assert query.params() == [
            ("f1", "OP"),
            ("j1", "OR"),
            ("f2", "OP"),
            ("j2", "AND"),
            ("f3", "a"),
            ("o3", "equals"),
            ("v3", "1"),
            ("f4", "CP"),
            ("f5", "CP"),
        ]

    def test_group_after_criterion_continues_numbering(self):
        query = BugQuery.keywords("x") & BugQuery.any_of(BugQuery.keywords("y"))
        assert [key for key, _ in query.params() if key[0] in "fj"] == [
            "f1",
            "f2",
            "j2",
            "f3",
            "f4",
        ]


class TestCombining:
    def test_documented_example(self):
        query = (
            BugQuery.component(Component.STABILIZATION, Component.KEYWORDING)
            & BugQuery.unresolved()
            & BugQuery.flag("sanity-check", FlagStatus.GRANTED)
            & BugQuery.without_tags("nattka:skip")
        )
        assert encoded(query) == (
            "component=Stabilization&component=Keywording&resolution=---"
            "&f1=flagtypes.name&o1=anywords&v1=sanity-check%2B"
            "&f2=tag&o2=nowordssubstr&v2=nattka%3Askip"
        )

    def test_same_key_values_are_unioned(self):
        query = BugQuery.component(Component.STABILIZATION) & BugQuery.component(
            Component.KEYWORDING
        )
        assert query.params() == [
            ("component", "Stabilization"),
            ("component", "Keywording"),
        ]

    def test_duplicate_values_are_dropped(self):
        query = BugQuery.ids((1, 2)) & BugQuery.ids((2, 3))
        assert query.params() == [("id", "1"), ("id", "2"), ("id", "3")]

    def test_right_hand_limit_wins(self):
        left = BugQuery().paged(10)
        assert (left & BugQuery().paged(20)).limit == 20
        assert (left & BugQuery()).limit == 10

    def test_operands_are_unchanged(self):
        left = BugQuery.ids((1,))
        right = BugQuery.unresolved()
        left & right
        assert left.params() == [("id", "1")]
        assert right.params() == [("resolution", "---")]


class TestPaging:
    def test_paged(self):
        query = BugQuery.unresolved().paged(100, 200)
        assert query.params()[-2:] == [("limit", "100"), ("offset", "200")]

    def test_offset_zero_is_omitted(self):
        assert ("offset", "0") not in BugQuery().paged(100).params()

    @pytest.mark.parametrize("limit", (0, -1))
    def test_rejects_non_positive_limit(self, limit):
        # bugzilla treats limit=0 as unlimited and silently drops the offset
        with pytest.raises(BugzillaUsageError, match="limit must be positive"):
            BugQuery().paged(limit)

    def test_rejects_negative_offset(self):
        with pytest.raises(BugzillaUsageError, match="offset"):
            BugQuery().paged(10, -1)

    def test_order(self):
        query = BugQuery(order="bug_id")
        assert query.params() == [("order", "bug_id")]


class TestBatches:
    def test_no_splittable_axis_yields_itself(self):
        query = BugQuery.unresolved()
        assert list(query.batches()) == [query]

    def test_small_query_is_a_single_batch(self):
        query = BugQuery.ids((1, 2, 3))
        assert [b.params() for b in query.batches()] == [query.params()]

    def test_ids_are_split(self):
        query = BugQuery.ids(range(900000, 902000))
        batches = list(query.batches())
        assert len(batches) > 1
        for batch in batches:
            assert len(urllib.parse.urlencode(batch.params())) <= MAX_URL_LENGTH

    def test_split_is_lossless_and_ordered(self):
        ids = list(range(900000, 902000))
        batches = BugQuery.ids(ids).batches()
        assert [int(v) for b in batches for k, v in b.params() if k == "id"] == ids

    def test_fixed_params_are_repeated(self):
        query = BugQuery.ids(range(900000, 902000)) & BugQuery.unresolved()
        for batch in query.batches():
            assert ("resolution", "---") in batch.params()

    def test_package_list_is_split(self):
        packages = [
            f"=dev-libs/verylongpackagename{i}-1.2.3_p20240101-r3" for i in range(200)
        ]
        batches = list(BugQuery.package_list_any(packages).batches())
        assert len(batches) > 1
        assert [
            v for b in batches for k, v in b.params() if k.startswith("v")
        ] == packages

    def test_base_length_shrinks_batches(self):
        ids = list(range(900000, 902000))
        wide = len(list(BugQuery.ids(ids).batches(base_length=0)))
        narrow = len(list(BugQuery.ids(ids).batches(base_length=4000)))
        assert narrow > wide

    def test_widest_axis_is_chosen(self):
        query = BugQuery.ids((1, 2)) & BugQuery.package_list_any(
            f"=dev-libs/pkg{i}-1" for i in range(400)
        )
        for batch in query.batches():
            # the narrow axis rides along in every batch
            assert [v for k, v in batch.params() if k == "id"] == ["1", "2"]

    def test_max_length_is_honoured(self):
        query = BugQuery.ids(range(900000, 902000))
        for batch in query.batches(max_length=500):
            assert len(urllib.parse.urlencode(batch.params())) <= 500
