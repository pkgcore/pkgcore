from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.restricts import CategoryDep
from pkgcore.ebuild.cpv import VersionedCPV
from pkgcore.repository import filtered
from pkgcore.repository.util import SimpleTree
from pkgcore.restrictions import packages, values


class TestVisibility:
    def setup_repos(self, restrictions=None):
        repo = SimpleTree(
            {
                "dev-util": {"diffball": ["1.0", "0.7"], "bsdiff": ["0.4.1", "0.4.2"]},
                "dev-lib": {"fake": ["1.0", "1.0-r1"]},
            }
        )
        if restrictions is None:
            restrictions = atom("dev-util/diffball")
        vrepo = filtered.tree(repo, restrictions)
        return repo, vrepo

    def test_filtering(self):
        repo, vrepo = self.setup_repos()
        a = atom("dev-lib/fake")
        a2 = atom("dev-util/diffball")
        assert sorted(vrepo.itermatch(a)) == sorted(repo.itermatch(a))
        assert sorted(vrepo.itermatch(a2)) == []
        repo, vrepo = self.setup_repos(atom("=dev-util/diffball-1.0"))
        assert sorted(vrepo.itermatch(a)) == sorted(repo.itermatch(a))
        assert sorted(vrepo.itermatch(a2)) == sorted(
            [VersionedCPV("dev-util/diffball-0.7")]
        )
        repo, vrepo = self.setup_repos(
            packages.PackageRestriction(
                "package",
                values.OrRestriction(
                    *[values.StrExactMatch(x) for x in ("diffball", "fake")]
                ),
            )
        )
        assert sorted(vrepo.itermatch(packages.AlwaysTrue)) == sorted(
            repo.itermatch(atom("dev-util/bsdiff"))
        )

        # check sentinel value handling.
        vrepo = filtered.tree(repo, a2, sentinel_val=True)
        assert sorted(x.cpvstr for x in vrepo) == sorted(
            ["dev-util/diffball-0.7", "dev-util/diffball-1.0"]
        )

    def test_iter(self):
        repo, vrepo = self.setup_repos(
            packages.PackageRestriction(
                "package",
                values.OrRestriction(
                    *[values.StrExactMatch(x) for x in ("diffball", "fake")]
                ),
            )
        )
        assert sorted(vrepo) == sorted(repo.itermatch(atom("dev-util/bsdiff")))

    def test_categories_api(self):
        # filter to just dev-util/diffball; this confirms that empty categories are filter,
        # and that filtering of a package (leaving one in a category still) doesn't filter the category.
        _, vrepo = self.setup_repos(
            packages.OrRestriction(CategoryDep("dev-lib"), atom("dev-util/bsdiff"))
        )
        assert sorted(vrepo.categories) == sorted(
            [
                "dev-lib",
                "dev-util",
            ]
        ), (
            "category filtering must not filter dev-lib even if there are no packages left post filtering"
        )

    def test_packages_api(self):
        _, vrepo = self.setup_repos(atom("dev-util/diffball"))
        assert sorted(vrepo.packages["dev-util"]) == ["bsdiff"]

    def test_versions_api(self):
        _, vrepo = self.setup_repos(atom("=dev-util/diffball-1.0"))
        assert sorted(vrepo.versions[("dev-util", "diffball")]) == ["0.7"]
