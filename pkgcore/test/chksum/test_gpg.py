# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from twisted.trial import unittest
from pkgcore.chksum import gpg


class TestSkipSignatures(unittest.TestCase):
    
    def test_skipping(self):
        d = ["asdf",
            "fdsa",
            "-----BEGIN PGP SIGNATURE-----",
            "this isn't a valid sig...",
            "-----END PGP SIGNATURE-----",
            "foon"]
        self.assertEqual(list(gpg.skip_signatures(d)), [d[0], d[1], d[-1]])
