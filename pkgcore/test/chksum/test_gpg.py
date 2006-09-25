# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.chksum import gpg

class TestSkipSignatures(TestCase):
    
    def test_simple_skipping(self):
        for header in ([],
            ["-----BEGIN PGP SIGNED MESSAGE-----\n", "Hash: Sha1\n", "\n"]):
            d = ["asdf\n",
                "fdsa\n",
                "-----BEGIN PGP SIGNATURE-----\n",
                "this isn't a valid sig...\n",
                "-----END PGP SIGNATURE-----\n",
                "foon\n"]
            d2 = header + d
            parsed = list(gpg.skip_signatures(d2))
            required = [d[0], d[1], d[-1]]
            self.assertEqual(parsed, required, msg="%r != %r for header %r" % 
                (parsed, required, header))

    def test_signed_signed(self):
        d = ["-----BEGIN PGP SIGNED MESSAGE-----\n",
            "Hash: SHA1\n",
            "\n",
            "- -----BEGIN PGP SIGNED MESSAGE-----\n",
            "Hash: SHA1\n",
            "\n",
            "blah\n",
            "- -----BEGIN PGP SIGNATURE-----\n",
            "Version: GnuPG v1.4.3 (GNU/Linux)\n",
            "\n",
            "iD8DBQFEViv+aGfFFLhbXWkRAo+lAJ93s57QA2lW5BE1FdmEc3uzijpJrwCfcE6j",
            "3Nzn/8wExwZ5eUacC/HoSo8=",
            "=oBur",
            "- -----END PGP SIGNATURE-----\n",
            "foon\n",
            "-----BEGIN PGP SIGNATURE-----\n",
            " not valid...\n",
            "-----END PGP SIGNATURE-----\n",
            "asdf\n"]
        self.assertEqual(list(gpg.skip_signatures(d)),
            ["blah\n", "foon\n", "asdf\n"])
