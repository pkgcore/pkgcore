from pkgcore.pkgsets import installed
from pkgcore.repository.util import SimpleTree


class FakePkg:

    package_is_real = True
    is_supported = True

    def __init__(self, cat, pn, ver):
        self.cat = cat
        self.pn = pn
        self.ver = ver

    @property
    def slotted_atom(self):
        return f"{self.cat}/{self.pn}"

    @property
    def versioned_atom(self):
        return f"{self.cat}/{self.pn}-{self.ver}"


class TestInstalled:

    def test_iter(self):
        fake_vdb = SimpleTree(
            {"dev-util": {
                "diffball": ["1.0"],
                "bsdiff": ["1.2", "1.3"],
                }
            }, pkg_klass=FakePkg)

        ipkgset = installed.Installed([fake_vdb])
        pkgs = sorted(["dev-util/diffball", "dev-util/bsdiff", "dev-util/bsdiff"])
        assert pkgs == sorted(ipkgset)

        vpkgset = installed.VersionedInstalled([fake_vdb])
        cpvs = sorted(["dev-util/diffball-1.0", "dev-util/bsdiff-1.2", "dev-util/bsdiff-1.3"])
        assert cpvs == sorted(vpkgset)
