# Copyright: 2015 Tim Harder
# License: GPL2/BSD

import os
import shutil
import stat
from tempfile import NamedTemporaryFile
import textwrap

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
        # by default files are required
        self.assertRaises(
            errors.ParsingError, load_make_conf,
            d, pjoin(self.dir, 'make.globals'))
        # should return empty dict when not required
        load_make_conf(d, pjoin(self.dir, 'make.conf'), required=False)
        self.assertEqual({}, d)

        # unreadable file
        d = {}
        with NamedTemporaryFile() as f:
            shutil.copyfile(pjoin(const.CONFIG_PATH, 'make.globals'), f.name)
            os.chmod(f.name, stat.S_IWUSR)
            self.assertRaises(
                errors.PermissionDeniedError, load_make_conf, d, f.name)

        # overrides and incrementals
        with NamedTemporaryFile() as f:
            f.write('DISTDIR=foo\nACCEPT_LICENSE=foo\n')
            f.flush()
            d = {}
            load_make_conf(d, pjoin(const.CONFIG_PATH, 'make.globals'))
            load_make_conf(d, f.name, allow_sourcing=True, incrementals=True)
            self.assertEqual('foo', d['DISTDIR'])
            self.assertEqual(
                ' '.join([default_make_conf['ACCEPT_LICENSE'], 'foo']),
                d['ACCEPT_LICENSE'])

        # load files from dir
        with NamedTemporaryFile(prefix='a', dir=self.dir) as f:
            with NamedTemporaryFile(prefix='z', dir=self.dir) as g:
                shutil.copyfile(pjoin(const.CONFIG_PATH, 'make.globals'), f.name)
                g.write('DISTDIR=foo\n')
                g.flush()
                d = {}
                load_make_conf(d, self.dir)
                self.assertEqual(
                    default_make_conf['ACCEPT_LICENSE'], d['ACCEPT_LICENSE'])
                self.assertEqual('foo', d['DISTDIR'])

    def test_load_repos_conf(self):
        # default file
        defaults, repos_conf = load_repos_conf(
            pjoin(const.CONFIG_PATH, 'repos.conf'))
        self.assertIn('gentoo', repos_conf)

        # nonexistent file
        self.assertRaises(
            errors.ParsingError, load_repos_conf,
            pjoin(self.dir, 'repos.conf'))

        # unreadable file
        with NamedTemporaryFile() as f:
            shutil.copyfile(pjoin(const.CONFIG_PATH, 'repos.conf'), f.name)
            os.chmod(f.name, stat.S_IWUSR)
            self.assertRaises(
                errors.PermissionDeniedError, load_repos_conf, f.name)

        # blank file
        with NamedTemporaryFile() as f:
            self.assertRaises(
                errors.ConfigurationError, load_repos_conf, f.name)

        # missing location parameter
        with NamedTemporaryFile() as f:
            f.write(textwrap.dedent('''\
                [foo]
                sync-uri = git://foo.git'''))
            f.flush()
            self.assertRaises(
                errors.ParsingError, load_repos_conf, f.name)

        # undefined main repo with 'gentoo' missing
        with NamedTemporaryFile() as f:
            f.write(textwrap.dedent('''\
                [foo]
                location = /var/gentoo/repos/foo'''))
            f.flush()
            self.assertRaises(
                errors.ConfigurationError, load_repos_conf, f.name)

        # repo priority sorting
        with NamedTemporaryFile(prefix='a', dir=self.dir) as f:
            with NamedTemporaryFile(prefix='z', dir=self.dir) as g:
                shutil.copyfile(pjoin(const.CONFIG_PATH, 'repos.conf'), f.name)
                g.write(textwrap.dedent('''\
                    [bar]
                    location = /var/gentoo/repos/bar

                    [foo]
                    location = /var/gentoo/repos/foo
                    priority = 10'''))
                g.flush()

                defaults, repos = load_repos_conf(self.dir)
                self.assertEqual('gentoo', defaults['main-repo'])
                self.assertEqual(['foo', 'bar', 'gentoo'], repos.keys())
