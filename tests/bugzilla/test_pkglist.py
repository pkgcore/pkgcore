import pytest

from pkgcore.bugzilla.errors import PackageListError
from pkgcore.bugzilla.pkglist import PackageList, PackageListEntry, parse_atom
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import MalformedAtom


class TestParseAtom:
    @pytest.mark.parametrize(
        ("token", "expected"),
        (
            ("dev-python/foo-1.2", "=dev-python/foo-1.2"),
            ("=dev-python/foo-1.2", "=dev-python/foo-1.2"),
            ("dev-python/foo", "dev-python/foo"),
            ("dev-python/foo:3", "dev-python/foo:3"),
            ("=dev-libs/x-1.2.3_p1-r2", "=dev-libs/x-1.2.3_p1-r2"),
            (">=dev-libs/x-1.2", ">=dev-libs/x-1.2"),
        ),
    )
    def test_valid(self, token, expected):
        assert parse_atom(token) == atom(expected)

    @pytest.mark.parametrize(
        "token",
        (
            "",
            "not-an-atom",
            "!dev-libs/foo",
            "dev-libs/foo[bar]",
            "dev-libs/foo:*",
        ),
    )
    def test_invalid(self, token):
        with pytest.raises(MalformedAtom):
            parse_atom(token)


class TestPackageList:
    def test_empty(self):
        pkglist = PackageList()
        assert not pkglist
        assert pkglist.entries == ()
        assert pkglist.atoms == ()
        assert str(pkglist) == ""

    def test_blank_is_falsy(self):
        assert not PackageList("\n  \r\n")

    def test_parse(self):
        pkglist = PackageList(
            "  dev-python/foo-1.2 amd64 x86  # careful\n"
            "dev-libs/bar\n"
            "\n"
            "# standalone comment\n"
        )
        first, second, blank, comment = pkglist.entries
        assert (first.lineno, first.pkg, first.keywords) == (
            1,
            atom("=dev-python/foo-1.2"),
            ("amd64", "x86"),
        )
        assert first.comment == "# careful"
        assert not first.is_blank
        assert (second.pkg, second.keywords, second.comment) == (
            atom("dev-libs/bar"),
            (),
            "",
        )
        assert blank.is_blank and blank.comment == ""
        assert comment.is_blank and comment.comment == "# standalone comment"
        assert pkglist.atoms == (atom("=dev-python/foo-1.2"), atom("dev-libs/bar"))

    def test_hash_needs_leading_whitespace_to_start_a_comment(self):
        (entry,) = PackageList("dev-libs/a amd64#x86").entries
        assert entry.comment == ""
        assert entry.keywords == ("amd64#x86",)

    @pytest.mark.parametrize("eol", ("\n", "\r\n"))
    def test_round_trip(self, eol):
        text = eol.join(
            ("  dev-libs/a amd64  # note", "dev-libs/b *", "", "dev-libs/c")
        )
        assert str(PackageList(text)) == text

    def test_round_trip_trailing_newline(self):
        text = "dev-libs/a amd64\r\n"
        assert str(PackageList(text)) == text

    def test_malformed_atom_reports_line(self):
        pkglist = PackageList("dev-libs/a\nnot an atom\n", bug_id=42)
        with pytest.raises(PackageListError) as excinfo:
            assert pkglist.entries
        assert excinfo.value.lineno == 2
        assert excinfo.value.bug_id == 42
        assert "bug 42, line 2" in str(excinfo.value)

    def test_parse_is_lazy(self):
        # constructing must not raise, only looking at the entries does
        pkglist = PackageList("not an atom")
        with pytest.raises(PackageListError):
            assert pkglist.entries

    def test_entries_cached(self):
        pkglist = PackageList("dev-libs/a amd64")
        assert pkglist.entries is pkglist.entries

    def test_keywords_for(self):
        pkglist = PackageList("dev-libs/a amd64 x86\ndev-libs/b arm")
        assert pkglist.keywords_for(atom("dev-libs/a")) == ("amd64", "x86")
        assert pkglist.keywords_for(atom("dev-libs/b")) == ("arm",)
        assert pkglist.keywords_for(atom("dev-libs/nope")) == ()

    def test_build(self):
        pkglist = PackageList.build(
            (
                (atom("=dev-libs/a-1"), ("amd64", "x86")),
                (atom("dev-libs/b"), ()),
            )
        )
        assert str(pkglist) == "=dev-libs/a-1 amd64 x86\ndev-libs/b"
        assert pkglist.atoms == (atom("=dev-libs/a-1"), atom("dev-libs/b"))

    def test_equality_and_hash(self):
        assert PackageList("dev-libs/a") == PackageList("dev-libs/a")
        assert PackageList("dev-libs/a") != PackageList("dev-libs/b")
        assert PackageList("dev-libs/a") != "dev-libs/a"
        assert len({PackageList("dev-libs/a"), PackageList("dev-libs/a")}) == 1

    def test_immutable(self):
        pkglist = PackageList("dev-libs/a")
        with pytest.raises(AttributeError):
            pkglist.text = "dev-libs/b"


class TestExpand:
    def test_all_keywords(self):
        pkglist = PackageList("dev-libs/a *\n")
        assert (
            str(pkglist.expand(lambda pkg: ("alpha", "hppa")))
            == "dev-libs/a alpha hppa\n"
        )

    def test_all_keywords_empty_collapses_to_dash(self):
        assert str(PackageList("dev-libs/a *").expand(lambda pkg: ())) == "dev-libs/a -"

    def test_same_keywords(self):
        pkglist = PackageList("dev-libs/a amd64 x86\ndev-libs/b ^\n")
        expanded = pkglist.expand(lambda pkg: ())
        assert str(expanded) == "dev-libs/a amd64 x86\ndev-libs/b amd64 x86\n"

    def test_same_keywords_chains(self):
        pkglist = PackageList("dev-libs/a *\ndev-libs/b ^\ndev-libs/c ^")
        expanded = pkglist.expand(lambda pkg: ("arm",))
        assert str(expanded) == "dev-libs/a arm\ndev-libs/b arm\ndev-libs/c arm"

    def test_same_keywords_on_first_line(self):
        with pytest.raises(PackageListError, match="no line above"):
            PackageList("dev-libs/a ^", bug_id=7).expand(lambda pkg: ())

    def test_mixed_sentinel_and_literal(self):
        pkglist = PackageList("dev-libs/a * ppc")
        assert str(pkglist.expand(lambda pkg: ("amd64",))) == "dev-libs/a amd64 ppc"

    def test_preserves_line_endings(self):
        pkglist = PackageList("dev-libs/a *\r\ndev-libs/b ^\r\n")
        assert str(pkglist.expand(lambda pkg: ("arm",))) == (
            "dev-libs/a arm\r\ndev-libs/b arm\r\n"
        )

    def test_preserves_untouched_lines(self):
        text = "   dev-libs/a amd64   # keep me\ndev-libs/b *\n"
        expanded = PackageList(text).expand(lambda pkg: ("arm",))
        assert str(expanded) == "   dev-libs/a amd64   # keep me\ndev-libs/b arm\n"

    def test_keeps_comment_on_rewritten_line(self):
        expanded = PackageList("dev-libs/a *  # why").expand(lambda pkg: ("arm",))
        assert str(expanded) == "dev-libs/a arm  # why"

    def test_no_sentinels_returns_self(self):
        pkglist = PackageList("dev-libs/a amd64\n")
        assert pkglist.expand(lambda pkg: ("arm",)) is pkglist

    def test_blank_lines_do_not_reset_previous(self):
        pkglist = PackageList("dev-libs/a amd64\n\n# note\ndev-libs/b ^")
        assert str(pkglist.expand(lambda pkg: ())) == (
            "dev-libs/a amd64\n\n# note\ndev-libs/b amd64"
        )


class TestPackageListEntry:
    def test_with_keywords_keeps_indent_and_comment(self):
        (entry,) = PackageList("   dev-libs/a amd64  # note").entries
        updated = entry.with_keywords(("arm", "ppc"))
        assert updated.raw == "   dev-libs/a arm ppc  # note"
        assert updated.keywords == ("arm", "ppc")
        assert updated.lineno == entry.lineno

    def test_with_keywords_on_blank_is_a_noop(self):
        (entry,) = PackageList("# just a comment").entries
        assert entry.with_keywords(("arm",)) is entry

    def test_frozen(self):
        entry = PackageListEntry(1, "dev-libs/a", atom("dev-libs/a"))
        with pytest.raises(AttributeError):
            entry.lineno = 2
