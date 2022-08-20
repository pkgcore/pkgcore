from pkgcore.restrictions import packages, util, values


class TestCollectPackageRestrictions:

    def test_collect_all(self):
        prs = [packages.PackageRestriction("category", values.AlwaysTrue)] * 10
        assert prs == list(util.collect_package_restrictions(
            packages.AndRestriction(
                packages.OrRestriction(), packages.AndRestriction(), *prs)))

    def test_collect_specific(self):
        prs = {
            x: packages.PackageRestriction(x, values.AlwaysTrue)
            for x in ("category", "package", "version", "iuse")
        }

        r = packages.AndRestriction(
            packages.OrRestriction(*prs.values()), packages.AlwaysTrue)
        for k, v in prs.items():
            assert [v] == list(util.collect_package_restrictions(r, attrs=[k]))

        r = packages.AndRestriction(packages.OrRestriction(
            *prs.values()), *prs.values())
        for k, v in prs.items():
            assert [v] * 2 == list(util.collect_package_restrictions(r, attrs=[k]))
