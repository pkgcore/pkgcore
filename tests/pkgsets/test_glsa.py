import pytest

from pkgcore.ebuild import atom, cpv
from pkgcore.pkgsets import glsa
from pkgcore.restrictions.packages import OrRestriction
from pkgcore.restrictions.restriction import AlwaysBool
from pkgcore.test.misc import mk_glsa

pkgs_set = (
    ("dev-util/diffball", ([], ["~>=0.7-r1"])),
    ("dev-util/bsdiff", ([">=2"], [">1"])),
)


class TestGlsaDirSet:

    def mk_glsa(self, tmp_path, feed):
        for idx, data in enumerate(feed):
            (tmp_path / f"glsa-200611-{idx:02d}.xml").write_text(mk_glsa(data))

    @pytest.mark.parametrize(("vuln_range", "ver_matches", "ver_nonmatches"), (
        pytest.param(">=1-r2", ["1-r2", "1-r7", "2"], ["0", "1"], id="ge"),
        pytest.param(">1-r2", ["1-r7", "2"], ["0", "1", "1-r2"], id="gt"),
        pytest.param("<=1-r2", ["1", "1-r1"], ["1-r3", "2"], id="le"),
        pytest.param("<1-r2", ["1", "1-r0"], ["1-r2", "2"], id="lt"),
        pytest.param("=1-r2", ["1-r2"], ["1-r3", "1", "2"], id="eq"),
        pytest.param("=1*", ["1-r2", "1.0.2", "10"], ["2", "3", "0"], id="eq_glob"),
        pytest.param("~>=1-r2", ["1-r2", "1-r7"], ["2", "1-r1", "1"], id="rge"),
        pytest.param("~>1-r1", ["1-r2", "1-r6"], ["2", "1-r1", "1"], id="rgt"),
        pytest.param("~<=1-r2", ["1-r2", "1", "1-r1"], ["2", "0.9", "1-r3"], id="rle"),
        pytest.param("~<1-r2", ["1", "1-r1"], ["2", "0.9", "1-r2"], id="rlt"),
        pytest.param("~>=2", ["2", "2-r1"], ["1", "2_p1", "2.1", "3"], id="rge_r0"),
        pytest.param("~>2", ["2-r1", "2-r2"], ["1", "2", "2_p1", "2.1"], id="rgt_r0"),
        pytest.param("~<=2", ["2"], ["1", "2-r1", "2_p1", "3"], id="rle_r0"),
        pytest.param("~<2", [], ["1", "2", "2-r1", "2.1", "3"], id="rlt_r0"),
    ))
    def test_range(self, tmp_path, vuln_range, ver_matches, ver_nonmatches):
        self.mk_glsa(tmp_path, [("dev-util/diffball", ([], [vuln_range]))])
        restrict = list(OrRestriction(*tuple(glsa.GlsaDirSet(str(tmp_path)))))
        if len(restrict) == 0: # exception thrown
            restrict.append(AlwaysBool(negate=False))
        assert len(restrict) == 1
        restrict = restrict[0]
        for ver in ver_matches:
            pkg = cpv.VersionedCPV(f"dev-util/diffball-{ver}")
            assert restrict.match(pkg), f"pkg {pkg} must match for {vuln_range!r}: {restrict}"

        for ver in ver_nonmatches:
            pkg = cpv.VersionedCPV(f"dev-util/diffball-{ver}")
            assert not restrict.match(pkg), "pkg {pkg} must not match for {vuln_range!r}: {restrict}"

    def test_iter(self, tmp_path):
        self.mk_glsa(tmp_path, pkgs_set)
        g = glsa.GlsaDirSet(str(tmp_path))
        l = list(g)
        assert {x.key for x in l} ==  {'dev-util/diffball', 'dev-util/bsdiff'}

    def test_pkg_grouped_iter(self, tmp_path):
        self.mk_glsa(tmp_path, pkgs_set + (("dev-util/bsdiff", ([], ["~>=2-r1"])),))
        g = glsa.GlsaDirSet(str(tmp_path))
        l = list(g.pkg_grouped_iter(sorter=sorted))
        assert {x.key for x in l} == {'dev-util/diffball', 'dev-util/bsdiff'}
        # main interest is dev-util/bsdiff
        r = l[0]
        pkgs = [cpv.VersionedCPV(f"dev-util/bsdiff-{ver}")
                for ver in ("0", "1", "1.1", "2", "2-r1")]
        assert [x.fullver for x in pkgs if r.match(x)] == ["1.1", "2-r1"]

    def test_slots(self, tmp_path):
        slotted_pkgs_set = pkgs_set + (
            ("dev-util/pkgcheck", '1', ([">=2"], [">1"]), '*'),
        )
        self.mk_glsa(tmp_path, slotted_pkgs_set)
        g = glsa.GlsaDirSet(str(tmp_path))
        l = list(g)
        assert {x.key for x in l} == {'dev-util/diffball', 'dev-util/bsdiff', 'dev-util/pkgcheck'}
        restrict = OrRestriction(*tuple(glsa.GlsaDirSet(str(tmp_path))))
        assert restrict.match(atom.atom('=dev-util/pkgcheck-1-r1:1'))
        assert not restrict.match(atom.atom('=dev-util/pkgcheck-1:1'))
        assert not restrict.match(atom.atom('=dev-util/pkgcheck-2:1'))
        assert not restrict.match(atom.atom('=dev-util/pkgcheck-1:0'))
        assert not restrict.match(atom.atom('dev-util/pkgcheck:0'))
        assert not restrict.match(atom.atom('dev-util/pkgcheck'))
