from pkgcore.ebuild import triggers
from pkgcore.fs.contents import contentsSet
from pkgcore.fs.fs import fsSymlink


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
