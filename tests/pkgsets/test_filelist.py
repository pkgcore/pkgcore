import os

import pytest
from pkgcore import os_data
from pkgcore.ebuild.atom import atom
from pkgcore.pkgsets import filelist


class TestFileList:

    kls = staticmethod(filelist.FileList)

    @property
    def gid(self):
        grps = os.getgroups()
        if os_data.portage_gid in grps:
            return os_data.portage_gid
        try:
            return grps[0]
        except IndexError:
            return os.getgid()

    def gen_pkgset(self, tmp_path, contents):
        (tmp_path / 'file').write_text(contents)
        return self.kls(tmp_path / 'file', gid=self.gid)

    def test_contains(self, tmp_path):
        assert atom("x11-base/xorg-x11") in self.gen_pkgset(tmp_path, "x11-base/xorg-x11")

    def test_len(self, tmp_path):
        assert len(self.gen_pkgset(tmp_path, "x11-base/xorg-x11\ndev-util/diffball")) == 2

    def test_iter(self, tmp_path):
        assert set(self.gen_pkgset(tmp_path, "dev-util/diffball\ndev-util/bsdiff")) == \
            {atom(x) for x in ["dev-util/diffball", "dev-util/bsdiff"]}

    def test_add(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/diffball\n=dev-util/bsdiff-0.4")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.flush()

        assert {atom(line) for line in (tmp_path / 'file').read_text().splitlines()} == \
            set(map(atom, ("dev-util/diffball", "=dev-util/bsdiff-0.4",
            "dev-util/foon", "=dev-util/lib-1")))

    def test_remove(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "=dev-util/diffball-0.4\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        assert {line.strip() for line in (tmp_path / 'file').read_text().splitlines()} == \
            {"dev-util/bsdiff"}

    def test_subset_awareness(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        with pytest.raises(ValueError):
            sorted(s)

    def test_ignore_comments(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "#foon\ndev-util/bsdiff")
        assert [str(x) for x in s] == ['dev-util/bsdiff']


class TestWorldFile(TestFileList):

    kls = staticmethod(filelist.WorldFile)

    def test_add(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/bsdiff")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.add(atom("dev-util/mylib:2"))
        s.flush()
        assert {line.strip() for line in (tmp_path / 'file').read_text().splitlines()} == \
            {"dev-util/bsdiff", "dev-util/foon", "dev-util/lib", "dev-util/mylib:2"}

    def test_remove(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/diffball\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        assert {line.strip() for line in (tmp_path / 'file').read_text().splitlines()} == \
            {"dev-util/bsdiff"}

    def test_subset_awareness(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        sorted(s)

    def test_subset_awareness2(self, tmp_path, caplog):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        assert [str(x) for x in s] == ['dev-util/bsdiff']
        assert "set item 'world'" in caplog.text
