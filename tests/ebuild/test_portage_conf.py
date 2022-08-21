import binascii
import os
import shutil
import stat
import textwrap

import pytest

from pkgcore import const
from pkgcore import exceptions as base_errors
from pkgcore.config import errors as config_errors
from pkgcore.ebuild.portage_conf import PortageConfig
from snakeoil.osutils import pjoin

load_make_conf = PortageConfig.load_make_conf
load_repos_conf = PortageConfig.load_repos_conf


class TestMakeConf:

    def test_load_defaults(self):
        make_globals = {}
        load_make_conf(make_globals, pjoin(const.CONFIG_PATH, 'make.globals'))
        assert 'PORTAGE_TMPDIR' in make_globals

    def test_nonexistent_file(self, tmp_path):
        d = {}
        # by default files are required
        with pytest.raises(config_errors.ParsingError):
            load_make_conf(d, tmp_path / 'make.globals')
        # should return empty dict when not required
        load_make_conf(d, tmp_path / 'make.conf', required=False)
        assert not d

    @pytest.mark.skipif(os.getuid() == 0, reason="need to be non root")
    def test_unreadable_file(self, tmp_path):
        d = {}
        (path := tmp_path / 'file').touch()
        path.chmod(stat.S_IWUSR)
        with pytest.raises(base_errors.PermissionDenied):
            load_make_conf(d, path)

    def test_overrides_incrementals(self, tmp_path):
        (path := tmp_path / 'file').write_bytes(b'DISTDIR=foo\n')
        d = {}
        load_make_conf(d, pjoin(const.CONFIG_PATH, 'make.globals'))
        load_make_conf(d, path, allow_sourcing=True, incrementals=True)
        assert d['DISTDIR'] == 'foo'

    def test_load_make_conf_dir(self, tmp_path):
        # load files from dir and symlinked dir
        (make_conf_dir := tmp_path / 'make.conf').mkdir()
        (make_conf_dir / 'a').write_text('DISTDIR=foo\n')
        (make_conf_sym := tmp_path / 'make.conf.sym').symlink_to(make_conf_dir)

        d = {}
        load_make_conf(d, pjoin(const.CONFIG_PATH, 'make.globals'))
        sym_d = d.copy()
        load_make_conf(d, make_conf_dir)
        load_make_conf(sym_d, make_conf_sym)

        assert d == sym_d
        assert d['DISTDIR'] == 'foo'


class TestReposConf:

    def test_load_defaults(self):
        _, global_repos_conf = load_repos_conf(pjoin(const.CONFIG_PATH, 'repos.conf'))
        assert 'gentoo' in global_repos_conf

    def test_nonexistent_file(self, tmp_path):
        with pytest.raises(config_errors.ParsingError):
            load_repos_conf(tmp_path / 'repos.conf')

    @pytest.mark.skipif(os.getuid() == 0, reason="need to be non root")
    def test_unreadable_file(self, tmp_path):
        (path := tmp_path / 'file').touch()
        path.chmod(stat.S_IWUSR)
        with pytest.raises(base_errors.PermissionDenied):
            load_repos_conf(path)

    def test_blank_file(self, tmp_path, caplog):
        (path := tmp_path / 'file').touch()
        load_repos_conf(path)
        assert 'file is empty' in caplog.text

    def test_garbage_file(self, tmp_path):
        (path := tmp_path / 'file').write_bytes(binascii.b2a_hex(os.urandom(10)))
        with pytest.raises(config_errors.ConfigurationError):
            load_repos_conf(path)

    def test_missing_location(self, tmp_path, caplog):
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [foo]
            sync-uri = git://foo.git'''))
        load_repos_conf(path)
        assert "'foo' repo missing location setting" in caplog.text

    def test_bad_priority(self, tmp_path, caplog):
        # bad priority value causes fallback to the default
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [foo]
            priority = foo
            location = /var/gentoo/repos/foo
            [gentoo]
            location = /var/gentoo/repos/gentoo'''))
        defaults, repos = load_repos_conf(path)
        assert repos['foo']['priority'] == 0
        assert "'foo' repo has invalid priority setting" in caplog.text

    def test_overriding_defaults_same_file(self, tmp_path):
        # overriding defaults in the same file throws an exception from configparser
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [DEFAULT]
            main-repo = gentoo
            [DEFAULT]
            main-repo = foo

            [foo]
            priority = foo
            location = /var/gentoo/repos/foo
            [gentoo]
            location = /var/gentoo/repos/gentoo'''))
        with pytest.raises(config_errors.ConfigurationError):
            load_repos_conf(path)

    def test_undefined_main_repo(self, tmp_path):
        # undefined main repo with 'gentoo' missing
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [foo]
            location = /var/gentoo/repos/foo'''))
        with pytest.raises(config_errors.UserConfigError):
            load_repos_conf(path)

    def test_optional_default_section(self, tmp_path, caplog):
        # default section isn't required as long as gentoo repo exists
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [foo]
            location = /var/gentoo/repos/foo
            [gentoo]
            location = /var/gentoo/repos/gentoo'''))
        defaults, repos = load_repos_conf(path)
        assert defaults['main-repo'] == 'gentoo'
        assert list(repos.keys()) == ['foo', 'gentoo']
        assert not caplog.text

    def test_overriding_sections_same_file(self, tmp_path):
        # overriding sections in the same file throws an exception from configparser
        (path := tmp_path / 'file').write_text(textwrap.dedent('''\
            [DEFAULT]
            main-repo = foo
            [foo]
            priority = 3
            location = /var/gentoo/repos/gentoo
            [foo]
            location = /var/gentoo/repos/foo'''))
        with pytest.raises(config_errors.ConfigurationError):
            load_repos_conf(path)

    def test_load_repos_conf_dir(self, tmp_path):
        # repo priority sorting and dir/symlink scanning
        (repos_conf_dir := tmp_path / 'repos.conf').mkdir()
        shutil.copyfile(pjoin(const.CONFIG_PATH, 'repos.conf'), repos_conf_dir / 'repos.conf')
        (repos_conf_sym := tmp_path / 'repos.conf.sym').symlink_to(repos_conf_dir)

        (repos_conf_sym / 'file').write_text(textwrap.dedent('''\
            [bar]
            location = /var/gentoo/repos/bar

            [foo]
            location = /var/gentoo/repos/foo
            priority = 10'''))

        defaults, repos = load_repos_conf(repos_conf_dir)
        sym_defaults, sym_repos = load_repos_conf(repos_conf_sym)

        assert defaults == sym_defaults
        assert repos == sym_repos
        assert defaults['main-repo'] == 'gentoo'
        assert list(repos.keys()) == ['foo', 'bar', 'gentoo', 'binpkgs']
