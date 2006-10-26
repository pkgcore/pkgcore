# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.test import TestCase

from pkgcore.scripts import pmaint
from pkgcore.test.scripts import helpers


class CommandlineTest(TestCase, helpers.MainMixin):

    parser = helpers.mangle_parser(pmaint.OptionParser())
    main = staticmethod(pmaint.main)

    def test_parser(self):
        self.assertError(
            'need at least one directive; '
            '--sync is the only supported command currently (see --help)')
