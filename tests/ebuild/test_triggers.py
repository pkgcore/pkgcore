import os
from types import SimpleNamespace

import pytest

from pkgcore.ebuild import triggers
from pkgcore.fs import livefs
from pkgcore.fs.contents import contentsSet
from pkgcore.fs.fs import fsFile, fsSymlink


class fake_format_op:
    def __init__(self, image_dir):
        self.env = {"D": image_dir}


class fake_engine:
    observer = None


class TestFixImageSymlinks:
    image = "/var/tmp/portage/cat/pkg-1/image"

    def mk_cset(self):
        return contentsSet(
            [
                # absolute symlink pointing into $D
                fsSymlink(
                    f"{self.image}/usr/lib/foo.so",
                    f"{self.image}/usr/lib/foo.so.1",
                    strict=False,
                ),
                # symlink not pointing into $D
                fsSymlink(
                    f"{self.image}/usr/lib/bar.so", "/usr/lib/bar.so.1", strict=False
                ),
            ]
        )

    def run(self, cset):
        trig = triggers.FixImageSymlinks(fake_format_op(self.image))
        trig.trigger(fake_engine(), cset)
        return {x.location: x.target for x in cset.iterlinks()}

    def test_rewrites_symlink_into_image(self):
        targets = self.run(self.mk_cset())
        # leading $D stripped, forced into an abspath
        assert targets[f"{self.image}/usr/lib/foo.so"] == "/usr/lib/foo.so.1"
        # symlinks not pointing into $D are left untouched
        assert targets[f"{self.image}/usr/lib/bar.so"] == "/usr/lib/bar.so.1"


class TestUninstallIgnore:
    def mk_cset(self):
        return contentsSet(
            [
                fsFile("/lib/modules/6.1/foo.ko", strict=False),
                fsFile("/usr/bin/foo", strict=False),
            ]
        )

    def test_uninstall(self):
        existing, uninstall = self.mk_cset(), self.mk_cset()
        trig = triggers.UninstallIgnore(["/lib/modules/*"])
        trig.trigger(fake_engine(), existing, uninstall)
        assert sorted(x.location for x in uninstall) == ["/usr/bin/foo"]

    def test_replace(self):
        existing, uninstall, old = self.mk_cset(), self.mk_cset(), self.mk_cset()
        trig = triggers.UninstallIgnore(["/lib/modules/*"])
        trig.trigger(fake_engine(), existing, uninstall, old)
        assert sorted(x.location for x in uninstall) == ["/usr/bin/foo"]
        assert sorted(x.location for x in old) == ["/usr/bin/foo"]


def test_multilib_strict_without_settings():
    class domain:
        features = frozenset(["multilib-strict", "nostrip"])
        binary_repos_raw = ()

    assert None not in triggers.GenerateTriggers(domain, {})


@pytest.mark.parametrize(
    ("pending", "expected"),
    (
        (("new",), "._cfg0000_foo.conf"),
        (("new", "other"), "._cfg0002_foo.conf"),
        (("other",), "._cfg0001_foo.conf"),
    ),
)
def test_config_protect_reuses_newest_identical_cfg(tmp_path, pending, expected):
    (etc := tmp_path / "etc").mkdir()
    (etc / "foo.conf").write_text("old\n")
    for count, content in enumerate(pending):
        (etc / f"._cfg{count:04d}_foo.conf").write_text(f"{content}\n")
    (image := tmp_path / "image").write_text("new\n")
    live = livefs.gen_obj(str(etc / "foo.conf")).change_attributes(
        location="/etc/foo.conf"
    )
    install = contentsSet(
        [livefs.gen_obj(str(image)).change_attributes(location="/etc/foo.conf")]
    )
    engine = SimpleNamespace(offset=str(tmp_path), observer=None)
    triggers.ConfigProtectInstall().trigger(engine, contentsSet([live]), install)
    assert [os.path.basename(x.location) for x in install] == [expected]
