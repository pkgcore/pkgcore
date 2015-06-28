# Copyright: 2015 Tim Harder
# License: GPL2/BSD

from tempfile import NamedTemporaryFile

from snakeoil.osutils import pjoin
from snakeoil.test.mixins import TempDirMixin

from pkgcore import const
from pkgcore.config import errors
from pkgcore.ebuild.portage_conf import load_make_conf, load_repos_conf
from pkgcore.test import TestCase


class TestPortageConfig(TempDirMixin, TestCase):

    def test_load_make_conf(self):
        # default file
        default_make_conf = {}
        load_make_conf(
            default_make_conf, pjoin(const.CONFIG_PATH, 'make.globals'))
        self.assertIn('PORTAGE_TMPDIR', default_make_conf)

        # nonexistent file
        d = {}
        self.assertRaises(
            errors.ParsingError, load_make_conf,
            d, pjoin(self.dir, 'make.conf'))
        # should return empty dict when not required
        load_make_conf(d, pjoin(self.dir, 'make.conf'), required=False)
        self.assertEqual({}, d)

        # TODO: loading dirs

        # TODO: loading additional files and with incrementals and overrides

    def test_load_repos_conf(self):
        # default file
        defaults, repos_conf = load_repos_conf(
            pjoin(const.CONFIG_PATH, 'repos.conf'))
        self.assertIn('gentoo', repos_conf)

        # nonexistent file
        self.assertRaises(
            errors.ParsingError, load_repos_conf,
            pjoin(self.dir, 'repos.conf'))

        # blank file
        with NamedTemporaryFile() as f:
            self.assertRaises(
                errors.ConfigurationError, load_repos_conf, f.name)

        # TODO: priority sorting
