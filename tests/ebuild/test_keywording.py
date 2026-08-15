import pytest

from pkgcore.bugzilla import BugCategory
from pkgcore.bugzilla.pkglist import PackageList
from pkgcore.ebuild.keywording import (
    KeywordNoMatch,
    KeywordNoneLeft,
    KeywordNotSpecified,
    PackageInvalid,
    PackageListDoneAlready,
    PackageListEmpty,
    PackageMatchException,
    PackageNoMatch,
    can_stabilize_allarches,
    filter_prefix_keywords,
    match_packages,
    select_best_version,
    suggested_keywords,
)
from pkgcore.exceptions import PkgcoreException
from pkgcore.pytest.plugin import EbuildRepo

# prefix arches are here on purpose: they are what exercises the prefix filter
# through the ``*`` sentinel, and the unknown-keyword check reads arch.list
ARCHES = ("alpha", "amd64", "hppa", "amd64-linux", "sparc-freebsd", "x86-macos")

PKGS = {
    "test/amd64-testing-1": {"keywords": ["~amd64"]},
    "test/amd64-testing-2": {"keywords": ["~amd64"]},
    "test/amd64-testing-10": {"keywords": []},
    "test/amd64-testing-9999": {"keywords": [], "properties": "live"},
    "test/amd64-stable-1": {"keywords": ["amd64"]},
    "test/amd64-stable-10": {"keywords": ["~amd64"]},
    "test/amd64-stable-hppa-testing-1": {"keywords": ["~alpha", "amd64", "~hppa"]},
    "test/amd64-stable-hppa-testing-2": {"keywords": ["~alpha", "amd64", "~hppa"]},
    "test/mixed-keywords-1": {"keywords": ["~alpha", "amd64", "~hppa"]},
    "test/mixed-keywords-2": {"keywords": ["~alpha", "~amd64", "hppa"]},
    "test/mixed-keywords-3": {"keywords": ["~alpha", "~amd64", "~hppa"]},
    "test/mixed-keywords-4": {"keywords": ["~amd64"]},
    "test/prefix-keywords-1": {"keywords": ["amd64", "x86-macos"]},
    "test/prefix-keywords-2": {"keywords": ["~amd64", "~x86-macos"]},
}


@pytest.fixture(scope="session")
def repo(tmp_path_factory):
    """A repo shared by the whole module; metadata regenerates once."""
    # the shipped repo/make_repo fixtures are function scoped, and regenerating
    # metadata per test is the dominant cost here
    tree = EbuildRepo(
        str(tmp_path_factory.mktemp("keywording")), repo_id="test", arches=ARCHES
    )
    for cpvstr, attrs in PKGS.items():
        tree.create_ebuild(cpvstr, **attrs)
    tree.sync()
    return tree


def match(repo, text, **kwargs):
    """Resolve a package list written the way a bug would carry it"""
    kwargs.setdefault("stable", True)
    requested = [
        (entry.pkg, entry.keywords)
        for entry in PackageList(text).entries
        if entry.pkg is not None
    ]
    return [(pkg.cpvstr, kw) for pkg, kw in match_packages(repo, requested, **kwargs)]


class TestSelectBestVersion:
    def test_prefers_newest_keyworded(self, repo):
        matched = repo.match(PackageList("test/amd64-testing").atoms[0])
        assert select_best_version(matched).cpvstr == "test/amd64-testing-2"

    def test_ignores_live(self, repo):
        matched = [
            p
            for p in repo.match(PackageList("test/amd64-testing").atoms[0])
            if not p.keywords
        ]
        assert select_best_version(matched).cpvstr == "test/amd64-testing-10"

    def test_falls_back_to_newest(self, repo):
        matched = [
            p for p in repo.match(PackageList("test/amd64-testing").atoms[0]) if p.live
        ]
        assert select_best_version(matched).cpvstr == "test/amd64-testing-9999"

    def test_empty(self):
        assert select_best_version([]) is None


class TestFilterPrefixKeywords:
    def test_drops_prefix_arches(self):
        assert filter_prefix_keywords(["amd64", "x86-macos", "hppa"]) == [
            "amd64",
            "hppa",
        ]

    def test_keeps_plain_arches(self):
        assert filter_prefix_keywords(["amd64"]) == ["amd64"]


class TestSuggestedKeywords:
    def test_stable_is_limited_to_current_testing(self, repo):
        pkg = repo.match(PackageList("=test/mixed-keywords-3").atoms[0])[0]
        # amd64 and hppa are stable on other versions and ~arch here
        assert suggested_keywords(repo, pkg, stable=True) == frozenset(
            {"amd64", "hppa"}
        )

    def test_keywording_is_what_is_missing(self, repo):
        pkg = repo.match(PackageList("=test/mixed-keywords-4").atoms[0])[0]
        assert suggested_keywords(repo, pkg, stable=False) == frozenset(
            {"alpha", "hppa"}
        )

    def test_prefix_arches_are_never_suggested(self, repo):
        pkg = repo.match(PackageList("=test/prefix-keywords-2").atoms[0])[0]
        assert "x86-macos" not in suggested_keywords(repo, pkg, stable=True)


class TestSpecValidation:
    """Only the category-dependent rule lives here.

    Specs that simply aren't package atoms are rejected while parsing, by
    :func:`~pkgcore.bugzilla.pkglist.parse_atom`, and are tested there.
    """

    # a stabilization names one exact version; keywording may name a range
    STABLE_ONLY_REJECTS = (
        ">=test/amd64-testing-1",
        "test/amd64-testing",
        "test/amd64-testing:0",
    )

    @pytest.mark.parametrize("spec", STABLE_ONLY_REJECTS)
    def test_rejected_when_stabilizing(self, repo, spec):
        with pytest.raises(PackageInvalid):
            match(repo, f"{spec} amd64", stable=True)

    @pytest.mark.parametrize("spec", STABLE_ONLY_REJECTS)
    def test_accepted_when_keywording(self, repo, spec):
        assert match(repo, f"{spec} amd64", stable=False)

    def test_no_match(self, repo):
        with pytest.raises(PackageNoMatch, match="no match for package"):
            match(repo, "=test/no-such-package-1 amd64")

    def test_no_match_outranks_a_pending_keyword_complaint(self, repo):
        # an earlier line with no keywords is only reported at the end, so a
        # later unmatchable line must still raise
        with pytest.raises(PackageNoMatch):
            match(repo, "test/mixed-keywords-3\n=test/no-such-package-1\n")


class TestMatching:
    def test_versioned_list(self, repo):
        assert match(
            repo,
            """
            test/amd64-testing-1 amd64
            =test/amd64-testing-2 amd64
            test/amd64-stable-hppa-testing-1 hppa
            """,
        ) == [
            ("test/amd64-testing-1", ["amd64"]),
            ("test/amd64-testing-2", ["amd64"]),
            ("test/amd64-stable-hppa-testing-1", ["hppa"]),
        ]

    def test_keywording_picks_the_best_version(self, repo):
        assert match(repo, "test/amd64-testing alpha", stable=False) == [
            ("test/amd64-testing-2", ["alpha"])
        ]

    def test_tilde_prefixes_are_stripped(self, repo):
        assert match(repo, "test/amd64-testing ~alpha", stable=False) == [
            ("test/amd64-testing-2", ["alpha"])
        ]

    def test_comment_is_ignored(self, repo):
        assert match(repo, "test/amd64-testing-1 amd64  # why") == [
            ("test/amd64-testing-1", ["amd64"])
        ]

    def test_unknown_keyword(self, repo):
        with pytest.raises(KeywordNoMatch, match="incorrect keywords"):
            match(repo, "test/amd64-testing-1 nosucharch")


class TestSentinels:
    def test_all_keywords_when_stabilizing(self, repo):
        assert match(repo, "test/mixed-keywords-3 *") == [
            ("test/mixed-keywords-3", ["amd64", "hppa"])
        ]

    def test_all_keywords_when_keywording(self, repo):
        assert match(repo, "=test/mixed-keywords-4 *", stable=False) == [
            ("test/mixed-keywords-4", ["alpha", "hppa"])
        ]

    def test_all_keywords_alongside_explicit(self, repo):
        ((_, keywords),) = match(repo, "test/mixed-keywords-3 * alpha")
        assert keywords == ["amd64", "hppa", "alpha"]

    def test_same_keywords(self, repo):
        assert match(
            repo,
            """
            test/amd64-stable-hppa-testing-1 hppa
            test/mixed-keywords-3 ^
            """,
        ) == [
            ("test/amd64-stable-hppa-testing-1", ["hppa"]),
            ("test/mixed-keywords-3", ["hppa"]),
        ]

    def test_same_keywords_survives_only_new(self, repo):
        # ^ copies the keywords as written, before only_new prunes them, so
        # each line drops only what that version already carries
        assert match(
            repo,
            """
            test/amd64-testing-1 amd64 alpha
            test/amd64-testing-10 ^
            test/amd64-testing-2 ^
            """,
            stable=False,
            only_new=True,
        ) == [
            ("test/amd64-testing-1", ["alpha"]),
            ("test/amd64-testing-10", ["amd64", "alpha"]),
            ("test/amd64-testing-2", ["alpha"]),
        ]

    def test_same_keywords_on_first_line(self, repo):
        with pytest.raises(KeywordNoMatch, match="first line"):
            match(repo, "test/amd64-testing-1 ^")

    def test_no_keywords_skips_the_line(self, repo):
        assert match(
            repo,
            """
            test/amd64-testing-1 -
            test/amd64-testing-2 amd64
            """,
        ) == [("test/amd64-testing-2", ["amd64"])]


class TestCcArches:
    def test_empty_keywords_inherit_cc(self, repo):
        assert match(repo, "test/mixed-keywords-3", cc_arches=("amd64",)) == [
            ("test/mixed-keywords-3", ["amd64"])
        ]

    def test_keywords_are_narrowed_to_cc(self, repo):
        assert match(
            repo, "test/mixed-keywords-3 amd64 hppa", cc_arches=("amd64",)
        ) == [("test/mixed-keywords-3", ["amd64"])]

    def test_line_disjoint_from_cc_is_dropped(self, repo):
        assert match(
            repo,
            """
            test/mixed-keywords-3 hppa
            test/amd64-stable-hppa-testing-1 amd64
            """,
            cc_arches=("amd64",),
        ) == [("test/amd64-stable-hppa-testing-1", ["amd64"])]


class TestOnlyNew:
    def test_stable_drops_arches_already_stable(self, repo):
        assert match(
            repo, "test/amd64-stable-hppa-testing-1 amd64 hppa", only_new=True
        ) == [("test/amd64-stable-hppa-testing-1", ["hppa"])]

    def test_keywording_also_drops_testing_arches(self, repo):
        # ~amd64 already satisfies a keywording request for amd64
        with pytest.raises(PackageListDoneAlready):
            match(repo, "test/amd64-testing-1 amd64", stable=False, only_new=True)

    def test_stabilizing_does_not_treat_testing_as_done(self, repo):
        assert match(repo, "test/mixed-keywords-3 amd64", only_new=True) == [
            ("test/mixed-keywords-3", ["amd64"])
        ]


class TestFilterArch:
    def test_keeps_only_the_listed_arch(self, repo):
        assert match(
            repo, "test/mixed-keywords-3 amd64 hppa", filter_arch=("amd64",)
        ) == [("test/mixed-keywords-3", ["amd64"])]

    def test_everything_filtered_away(self, repo):
        with pytest.raises(PackageListEmpty, match="no packages match"):
            match(repo, "test/mixed-keywords-3 hppa", filter_arch=("amd64",))


class TestAllarches:
    def test_readds_candidates_past_the_filter(self, repo):
        # one arch team stabilizes on behalf of the rest
        ((_, keywords),) = match(
            repo,
            "test/mixed-keywords-3 amd64 hppa",
            filter_arch=("amd64",),
            allarches=True,
        )
        assert keywords == ["amd64", "hppa"]

    def test_readds_candidates_the_filter_excluded(self, repo):
        # the requested arch comes first, then whatever allarches adds
        ((_, keywords),) = match(
            repo,
            "test/mixed-keywords-4 amd64 hppa",
            filter_arch=("hppa",),
            allarches=True,
        )
        assert keywords == ["hppa", "amd64"]

    def test_ignored_without_a_filter(self, repo):
        assert match(repo, "test/mixed-keywords-3 amd64", allarches=True) == [
            ("test/mixed-keywords-3", ["amd64"])
        ]

    def test_ignored_when_keywording(self, repo):
        assert match(
            repo,
            "=test/mixed-keywords-4 alpha hppa",
            stable=False,
            filter_arch=("alpha",),
            allarches=True,
        ) == [("test/mixed-keywords-4", ["alpha"])]


class TestTerminalOutcomes:
    def test_empty_list(self, repo):
        with pytest.raises(PackageListEmpty, match="empty package list"):
            match(repo, "")

    def test_all_done_already(self, repo):
        with pytest.raises(PackageListDoneAlready):
            match(repo, "test/amd64-stable-1 amd64", only_new=True)

    def test_keywords_not_specified(self, repo):
        with pytest.raises(KeywordNotSpecified) as excinfo:
            match(repo, "test/mixed-keywords-3")
        assert excinfo.value.packages == ("=test/mixed-keywords-3",)

    def test_nothing_left_to_suggest(self, repo):
        # stable everywhere it is testing, and nothing was asked for
        with pytest.raises(KeywordNoneLeft):
            match(repo, "test/amd64-stable-1")

    def test_nothing_left_but_others_yielded(self, repo):
        # a partial result keeps the request interesting, so it is reported as
        # incomplete rather than as nothing-to-do
        with pytest.raises(KeywordNotSpecified):
            match(
                repo,
                """
                test/mixed-keywords-3 amd64
                test/amd64-stable-1
                """,
            )


class TestCanStabilizeAllarches:
    def test_all_arches_have_a_stable_version(self, repo):
        pkg = repo.match(PackageList("=test/mixed-keywords-3").atoms[0])[0]
        assert can_stabilize_allarches(repo, [(pkg, ["amd64", "hppa"])])

    def test_an_arch_has_never_been_stable(self, repo):
        pkg = repo.match(PackageList("=test/mixed-keywords-3").atoms[0])[0]
        assert not can_stabilize_allarches(repo, [(pkg, ["amd64", "alpha"])])

    def test_no_keywords_requested(self, repo):
        pkg = repo.match(PackageList("=test/mixed-keywords-3").atoms[0])[0]
        assert can_stabilize_allarches(repo, [(pkg, [])])


def test_notice_escapes_the_broad_handler():
    # a caller reporting broken requests must not swallow "nothing to do"
    assert issubclass(KeywordNoneLeft, PkgcoreException)
    assert not issubclass(KeywordNoneLeft, PackageMatchException)


class TestBugBinding:
    def bug(self, category=BugCategory.STABLEREQ, packages="", cc=()):
        from pkgcore.bugzilla import Bug

        return Bug(
            product=str(category.product),
            component=str(category.component),
            package_list=PackageList(packages),
            cc=tuple(cc),
        )

    def test_category_selects_stabilizing(self, repo):
        bug = self.bug(packages="test/amd64-testing-1 amd64")
        assert [(p.cpvstr, k) for p, k in bug.match_packages(repo)] == [
            ("test/amd64-testing-1", ["amd64"])
        ]

    def test_keywording_bug_allows_a_bare_atom(self, repo):
        bug = self.bug(BugCategory.KEYWORDREQ, "test/amd64-testing alpha")
        assert [(p.cpvstr, k) for p, k in bug.match_packages(repo)] == [
            ("test/amd64-testing-2", ["alpha"])
        ]

    def test_cc_supplies_the_arches(self, repo):
        bug = self.bug(
            packages="test/mixed-keywords-3", cc=("amd64@gentoo.org", "someone")
        )
        assert [(p.cpvstr, k) for p, k in bug.match_packages(repo)] == [
            ("test/mixed-keywords-3", ["amd64"])
        ]

    def test_cc_arches_survive_anonymous_truncation(self, repo):
        # without an api key bugzilla cuts every address at the @
        bug = self.bug(
            packages="test/mixed-keywords-3", cc=("amd64", "hppa", "someone")
        )
        assert [(p.cpvstr, k) for p, k in bug.match_packages(repo)] == [
            ("test/mixed-keywords-3", ["amd64", "hppa"])
        ]

    def test_allarches_keyword_is_honoured(self, repo):
        from pkgcore.bugzilla import Bug

        bug = Bug(
            product="Gentoo Linux",
            component="Stabilization",
            package_list=PackageList("test/mixed-keywords-3 amd64 hppa"),
            keywords=("ALLARCHES",),
        )
        ((_, keywords),) = bug.match_packages(
            repo, filter_arch=("amd64",), permit_allarches=True
        )
        assert keywords == ["amd64", "hppa"]

    def test_allarches_needs_opting_in(self, repo):
        from pkgcore.bugzilla import Bug

        bug = Bug(
            product="Gentoo Linux",
            component="Stabilization",
            package_list=PackageList("test/mixed-keywords-3 amd64 hppa"),
            keywords=("ALLARCHES",),
        )
        ((_, keywords),) = bug.match_packages(repo, filter_arch=("amd64",))
        assert keywords == ["amd64"]

    def test_malformed_list_surfaces_as_package_invalid(self, repo):
        bug = self.bug(packages="not an atom")
        with pytest.raises(PackageInvalid):
            list(bug.match_packages(repo))
