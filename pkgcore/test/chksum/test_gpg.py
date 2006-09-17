# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.chksum import gpg

class TestSkipSignatures(unittest.TestCase):
    
    def test_skipping(self):
        for header in ([],
            ["-----BEGIN PGP SIGNED MESSAGE-----\n", "Hash: Sha1\n", ""]):
            d = ["asdf",
                "fdsa",
                "-----BEGIN PGP SIGNATURE-----",
                "this isn't a valid sig...",
                "-----END PGP SIGNATURE-----",
                "foon"]
            d2 = header + d
            parsed = list(gpg.skip_signatures(d2))
            required = [d[0], d[1], d[-1]]
            self.assertEqual(parsed, required, msg="%r != %r for header %r" % 
                (parsed, required, header))
