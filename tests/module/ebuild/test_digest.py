import os
import tempfile

from snakeoil.data_source import local_source
from snakeoil.test import TestCase

from pkgcore import gpg
from pkgcore.ebuild import digest

# "Line too long" (and our custom more aggressive version of that)
# pylint: disable-msg=C0301,CPC01

digest_contents = \
"""MD5 98db1465629693fc434d4dc52db93838 Python-2.4.2.tar.bz2 7853169
RMD160 c511d2b76b5394742d285e71570a2bcd3c1fa871 Python-2.4.2.tar.bz2 7853169
SHA256 e163b95ee56819c0f3c58ef9278c30b9e49302c2f1a1917680ca894d33929f7e Python-2.4.2.tar.bz2 7853169
MD5 2fa54dd51b6a8f1c46e5baf741e90f7e python-2.4-patches-1.tar.bz2 7820
RMD160 313c0f4f4dea59290c42a9b2c8de1db159f1ca1b python-2.4-patches-1.tar.bz2 7820
SHA256 e22abe4394f1f0919aac429f155c00ec1b3fe94cdc302119059994d817cd30b5 python-2.4-patches-1.tar.bz2 7820"""
digest_chksum = (
    ("size", int(7853169)),
    ("md5", int("98db1465629693fc434d4dc52db93838", 16)),
    ("rmd160", int("c511d2b76b5394742d285e71570a2bcd3c1fa871", 16)),
    ("sha256", int("e163b95ee56819c0f3c58ef9278c30b9e49302c2f1a1917680ca894d33929f7e", 16))
)

# ripped straight from the glep
pure_manifest2 = \
"""AUX ldif-buffer-overflow-fix.diff 5007 RMD160 1354a6bd2687430b628b78aaf43f5c793d2f0704 SHA1 424e1dfca06488f605b9611160020227ecdd03ac
AUX procmime.patch 977 RMD160 39a51a4d654759b15d1644a79fb6e8921130df3c SHA1 d76929f6dfc2179281f7ccee5789aab4e970ba9e
EBUILD sylpheed-claws-1.0.5-r1.ebuild 3906 RMD160 cdd546c128db2dea7044437de01ec96e12b4f5bf SHA1 a84b49e76961d7a9100852b64c2bfbf9b053d45e
EBUILD sylpheed-claws-1.9.100.ebuild 4444 RMD160 89326038bfc694dafd22f10400a08d3f930fb2bd SHA1 8895342f3f0cc6fcbdd0fdada2ad8e23ce539d23
EBUILD sylpheed-claws-1.9.15.ebuild 4821 RMD160 ec0ff811b893084459fe5b17b8ba8d6b35a55687 SHA1 358278a43da244e1f4803ec4b04d6fa45c41ab4d
MISC ChangeLog 25770 RMD160 0e69dd7425add1560d630dd3367342418e9be776 SHA1 1210160f7baf0319de3b1b58dc80d7680d316d28
MISC metadata.xml 269 RMD160 39d775de55f9963f8946feaf088aa0324770bacb SHA1 4fd7b285049d0e587f89e86becf06c0fd77bae6d
DIST sylpheed-claws-1.0.5.tar.bz2 3268626 RMD160 f2708b5d69bc9a5025812511fde04eca7782e367 SHA1 d351d7043eef7a875df18a8c4b9464be49e2164b
DIST sylpheed-claws-1.9.100.tar.bz2 3480063 RMD160 72fbcbcc05d966f34897efcc1c96377420dc5544 SHA1 47465662b5470af5711493ce4eaad764c5bf02ca
DIST sylpheed-claws-1.9.15.tar.bz2 3481018 RMD160 b01d1af2df55806a8a8275102b10e389e0d98e94 SHA1 a17fc64b8dcc5b56432e5beb5c826913cb3ad79e
"""
pure_manifest2_chksums = {}
for x in pure_manifest2.split("\n"):
    l = x.split()
    if not l:
        continue
    i = iter(l[3:])
    chksum = [("size", int(l[2]))]
    chksum += [(k.lower(), int(v, 16)) for k, v in zip(i, i)]
    chksum = tuple(chksum)
    pure_manifest2_chksums.setdefault(l[0], {})[l[1]] = chksum
    del chksum, l, i


class TestManifest(TestCase):

    convert_source = staticmethod(lambda x:x)

    def get_manifest(self, data):
        fd, fn = tempfile.mkstemp()
        os.write(fd, data.encode())
        os.close(fd)
        try:
            return digest.parse_manifest(self.convert_source(fn))
        finally:
            os.unlink(fn)

    def test_gpg_filtering(self):
        # intentionally stick gpg signing midway through
        data = pure_manifest2.split("\n")
        s = "\n".join(data[0:2])
        s += f"\n{gpg.sig_header}\nasdf\n{gpg.sig_footer}\n"
        s += "\n".join(data[2:])
        # ensure it can parse it
        (dist, aux, ebuild, misc) = self.get_manifest(s)

    def test_manifest2(self):
        (dist, aux, ebuild, misc) = \
            self.get_manifest(pure_manifest2)

        for dtype, d in (("DIST", dist), ("AUX", aux),
            ("EBUILD", ebuild), ("MISC", misc)):
            req_d = pure_manifest2_chksums[dtype]
            self.assertEqual(sorted(req_d), sorted(d))
            for k, v in req_d.items():
                i1 = sorted(v)
                i2 = sorted(d[k].items())
                self.assertEqual(i1, i2, msg="{i1!r} != {i2!r}\nfor {dtype} {k}")


class TestManifestDataSource(TestManifest):
    convert_source = staticmethod(lambda x: local_source(x))
