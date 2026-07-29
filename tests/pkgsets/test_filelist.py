import os
import types

import pytest

from pkgcore import os_data
from pkgcore.config import errors
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
        (tmp_path / "file").write_text(contents)
        return self.kls(tmp_path / "file", gid=self.gid)

    def test_contains(self, tmp_path):
        assert atom("x11-base/xorg-x11") in self.gen_pkgset(
            tmp_path, "x11-base/xorg-x11"
        )

    def test_len(self, tmp_path):
        assert (
            len(self.gen_pkgset(tmp_path, "x11-base/xorg-x11\ndev-util/diffball")) == 2
        )

    def test_iter(self, tmp_path):
        assert set(self.gen_pkgset(tmp_path, "dev-util/diffball\ndev-util/bsdiff")) == {
            atom(x) for x in ["dev-util/diffball", "dev-util/bsdiff"]
        }

    def test_add(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/diffball\n=dev-util/bsdiff-0.4")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.flush()

        assert {
            atom(line) for line in (tmp_path / "file").read_text().splitlines()
        } == {
            atom("dev-util/diffball"),
            atom("=dev-util/bsdiff-0.4"),
            atom("dev-util/foon"),
            atom("=dev-util/lib-1"),
        }

    def test_remove(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "=dev-util/diffball-0.4\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        assert {
            line.strip() for line in (tmp_path / "file").read_text().splitlines()
        } == {"dev-util/bsdiff"}

    def test_subset_awareness(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        with pytest.raises(errors.ParsingError):
            sorted(s)

    def test_ignore_comments(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "#foon\ndev-util/bsdiff")
        assert [str(x) for x in s] == ["dev-util/bsdiff"]

    def test_nested_set(self, tmp_path):
        (tmp_path / "nested").write_text("dev-util/diffball")
        nested = self.kls(tmp_path / "nested", gid=self.gid)
        config = types.SimpleNamespace(
            objects=types.SimpleNamespace(pkgset={"nested": nested})
        )
        (tmp_path / "file").write_text("@nested\ndev-util/bsdiff")
        s = self.kls(tmp_path / "file", config=config, gid=self.gid)
        assert set(s) == {atom("dev-util/diffball"), atom("dev-util/bsdiff")}

    def test_nested_set_unknown(self, tmp_path):
        config = types.SimpleNamespace(objects=types.SimpleNamespace(pkgset={}))
        s = self.kls(tmp_path / "file", config=config, gid=self.gid)
        (tmp_path / "file").write_text("@nested\ndev-util/bsdiff")
        if self.kls.error_on_subsets:
            with pytest.raises(errors.ParsingError):
                sorted(s)
        else:
            assert [str(x) for x in s] == ["dev-util/bsdiff"]

    def test_nested_set_cycle(self, tmp_path):
        pkgsets = {}
        config = types.SimpleNamespace(objects=types.SimpleNamespace(pkgset=pkgsets))
        a = self.kls(tmp_path / "a", config=config, gid=self.gid)
        b = self.kls(tmp_path / "b", config=config, gid=self.gid)
        pkgsets["a"] = a
        pkgsets["b"] = b
        (tmp_path / "a").write_text("@b\n")
        (tmp_path / "b").write_text("@a\n")
        with pytest.raises(errors.ParsingError):
            sorted(a)


class TestWorldFile(TestFileList):
    kls = staticmethod(filelist.WorldFile)

    def test_add(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/bsdiff")
        s.add(atom("dev-util/foon"))
        s.add(atom("=dev-util/lib-1"))
        s.add(atom("dev-util/mylib:2"))
        s.flush()
        assert {
            line.strip() for line in (tmp_path / "file").read_text().splitlines()
        } == {"dev-util/bsdiff", "dev-util/foon", "dev-util/lib", "dev-util/mylib:2"}

    def test_remove(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "dev-util/diffball\ndev-util/bsdiff")
        s.remove(atom("=dev-util/diffball-0.4"))
        s.flush()
        assert {
            line.strip() for line in (tmp_path / "file").read_text().splitlines()
        } == {"dev-util/bsdiff"}

    def test_subset_awareness(self, tmp_path):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        sorted(s)

    def test_subset_awareness2(self, tmp_path, caplog):
        s = self.gen_pkgset(tmp_path, "@world\ndev-util/bsdiff")
        assert [str(x) for x in s] == ["dev-util/bsdiff"]
        assert "set item 'world'" in caplog.text
