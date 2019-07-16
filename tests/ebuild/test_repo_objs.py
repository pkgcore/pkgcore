# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import logging
import os
import re

import pytest
from snakeoil.data_source import data_source
from snakeoil.fileutils import touch

from pkgcore.ebuild import repo_objs, atom
from pkgcore.repository import errors as repo_errors


class TestMetadataXml(object):

    @staticmethod
    def get_metadata_xml(maintainers=(), local_use={}, longdescription=None):
        hs = ms = us = ls = ""
        if maintainers:
            ms = []
            for x in maintainers:
                ms.append(f"<email>{x[0]}</email>")
                if len(x) > 1:
                    ms[-1] = f"{ms[-1]}\n<name>{x[1]}</name>"
            ms = "<maintainer>%s</maintainer>\n" % "</maintainer><maintainer>".join(ms)
        if local_use:
            us = ['<use>']
            for flag, desc in local_use.items():
                us.append(f'<flag name="{flag}">{desc}</flag>')
            us.append('</use>')
            us = '\n'.join(us)
        if longdescription:
            ls = f"<longdescription>{longdescription}</longdescription>\n"
        s = \
f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
{hs}{ms}{us}{ls}</pkgmetadata>"""
        return repo_objs.MetadataXml(data_source(s.encode('utf-8')))

    def test_maintainers(self):
        # test non empty, multiple
        names = ("foo@gmail.com", "monkeybone@gmail.com")
        mx = self.get_metadata_xml(maintainers=tuple(
            (x,) for x in names))
        assert sorted(names) == sorted(str(m) for m in mx.maintainers)
        # test email/name integration.
        mx = self.get_metadata_xml(
            maintainers=(("funkymonkey@gmail.com",
                          "funky monkey \N{SNOWMAN}"),))
        assert ("funky monkey \N{SNOWMAN} <funkymonkey@gmail.com>",) == \
            tuple(str(m) for m in mx.maintainers)
        assert "funkymonkey@gmail.com" == mx.maintainers[0].email
        assert "funky monkey \N{SNOWMAN}" == mx.maintainers[0].name

        # test maintainer-needed
        s = \
f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
<!-- maintainer-needed -->
</pkgmetadata>"""
        mx = repo_objs.MetadataXml(data_source(s.encode('utf-8')))
        assert "maintainer-needed" == mx.maintainers[0].name

        # test empty -> maintainer-needed
        s = \
f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
</pkgmetadata>"""
        mx = repo_objs.MetadataXml(data_source(s.encode('utf-8')))
        assert "maintainer-needed" == mx.maintainers[0].name

    def test_local_use(self):
        # empty...
        assert dict() == self.get_metadata_xml().local_use

        local_use = {
            "foo": "description for foo",
            "bar": "description for bar (<pkg>app-foo/bar</pkg> required)",
        }
        metadata_xml = self.get_metadata_xml(local_use=local_use)
        pkg_tag_re = re.compile(r'</?pkg>')
        local_use = dict(
                (k, pkg_tag_re.sub('', v))
                for k, v in local_use.items())
        assert local_use == metadata_xml.local_use

    def test_longdesc(self):
        # empty...
        assert None == self.get_metadata_xml().longdescription
        s = \
"""
I saw the best minds of my generation destroyed by madness, starving
hysterical naked, dragging themselves throughout the negro streets at dawn
looking for an angry fix, angle-headed hipsters burning for the ancient
heavenly connection to the starry dynamo in the machinery of night, who
poverty and tatters and hollowed-eyed and high sat up smoking in the
supernatural darkness of cold-water flats floating across the tops of cities
contemplating jazz, who bared their brains to Heaven under the El and saw
Mohammedan angels staggering on tenement roofs illuminated, who passed
through universities with radiant cool eyes hallucinating Arkansas and
Blake-light tragedy among the scholars of war.
"""

        assert " ".join(s.split()) == self.get_metadata_xml(longdescription=s).longdescription


class TestRepoConfig(object):

    @pytest.fixture(autouse=True)
    def _setup(self, tmpdir):
        self.repo_path = str(tmpdir)
        self.profiles_base = os.path.join(self.repo_path, 'profiles')
        self.metadata_path = os.path.join(
            self.repo_path, repo_objs.RepoConfig.layout_offset)

    def test_nonexistent_repo(self):
        # Newly configured, nonexistent repos shouldn't cause issues.
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.location == 'nonexistent'

    def test_eapi(self, caplog):
        os.mkdir(self.profiles_base)
        eapi_path = os.path.join(self.profiles_base, 'eapi')

        # default EAPI
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'
        del repo_config

        # empty file
        touch(eapi_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'
        del repo_config

        # whitespace content
        with open(eapi_path, 'w+') as f:
            f.write('     \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'
        del repo_config

        # unknown EAPI
        with open(eapi_path, 'w+') as f:
            f.write('unknown_eapi')
        with pytest.raises(repo_errors.UnsupportedRepo) as excinfo:
            repo_objs.RepoConfig(self.repo_path)
        assert isinstance(excinfo.value.repo, repo_objs.RepoConfig)

        # known EAPI
        with open(eapi_path, 'w+') as f:
            f.write('6')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '6'
        del repo_config

        # bad data, good EAPI
        with open(eapi_path, 'w+') as f:
            f.write('4\nfoo\nbar')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '4'
        assert 'multiple EAPI lines detected:' in caplog.text
        caplog.clear()
        del repo_config

        # bad data, unknown EAPI
        with open(eapi_path, 'w+') as f:
            f.write('eapi\nfoo\nbar')
        with pytest.raises(repo_errors.UnsupportedRepo) as excinfo:
            repo_objs.RepoConfig(self.repo_path)
        assert isinstance(excinfo.value.repo, repo_objs.RepoConfig)
        assert 'multiple EAPI lines detected:' in caplog.text
        caplog.clear()

    def test_is_empty(self, caplog):
        caplog.set_level(logging.DEBUG)

        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.is_empty
        assert caplog.text == ''
        caplog.clear()
        del repo_config

        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.is_empty
        assert 'repo is empty:' in caplog.text
        caplog.clear()
        del repo_config

        # profiles dir exists
        os.mkdir(self.profiles_base)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert not repo_config.is_empty
        del repo_config

    def test_repo_name(self, caplog):
        # nonexistent file
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name is None
        del repo_config

        # empty file
        os.mkdir(os.path.dirname(self.metadata_path))
        touch(self.metadata_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name is None
        del repo_config

        # bad data formatting
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name repo')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name is None
        assert 'bash parse error' in caplog.text
        caplog.clear()
        del repo_config

        # bad data formatting + name
        with open(self.metadata_path, 'w') as f:
            f.write('foo bar\nrepo-name = repo0')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name == 'repo0'
        assert 'bash parse error' in caplog.text
        caplog.clear()
        del repo_config

        # unset
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name =')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name == ''
        del repo_config

        # whitespace
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name =  \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name == ''
        del repo_config

        # whitespace + name
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name = repo \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name == 'repo'
        del repo_config

        # regular name
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name = repo1')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_name == 'repo1'
        del repo_config

    def test_manifests(self):
        # nonexistent file
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.manifests == {
            'disabled': False,
            'strict': True,
            'thin': False,
            'signed': True,
            'hashes': repo_objs.RepoConfig.default_hashes,
            'required_hashes': repo_objs.RepoConfig.default_required_hashes,
        }
        del repo_config

        # regular data
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('manifest-hashes = foo\n')
            f.write('manifest-required-hashes = bar\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.manifests.hashes == ('size', 'foo')
        assert repo_config.manifests.required_hashes == ('size', 'bar')
        del repo_config

    def test_masters(self, caplog):
        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.masters == ()
        assert caplog.text == ''
        caplog.clear()
        del repo_config

        # nonempty repo
        os.mkdir(self.profiles_base)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.masters == ()
        assert "doesn't specify masters in metadata" in caplog.text
        caplog.clear()
        del repo_config

        # explicit empty masters for standalone repo
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('masters =\n')
        repo_config = repo_objs.RepoConfig(self.repo_path, config_name='foo')
        assert repo_config.masters == ()
        assert caplog.text == ''
        caplog.clear()
        del repo_config

        # overlay repo with masters
        with open(self.metadata_path, 'w') as f:
            f.write('masters = foo bar\n')
        repo_config = repo_objs.RepoConfig(self.repo_path, config_name='a')
        assert repo_config.masters == ('foo', 'bar')
        del repo_config

        # overlay repo with duplicate masters
        with open(self.metadata_path, 'w') as f:
            f.write('masters = foo bar foo baz\n')
        repo_config = repo_objs.RepoConfig(self.repo_path, config_name='b')
        assert repo_config.masters == ('foo', 'bar', 'baz')
        del repo_config

    def test_cache_format(self, caplog):
        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format == 'md5-dict'
        del repo_config

        # explicit empty setting
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('cache-formats =\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format is None
        del repo_config

        # unknown formats
        with open(self.metadata_path, 'w') as f:
            f.write('cache-formats = foo bar\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format == 'md5-dict'
        assert 'unknown cache format:' in caplog.text
        caplog.clear()
        del repo_config

        # known format
        with open(self.metadata_path, 'w') as f:
            f.write('cache-formats = pms\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format == 'pms'
        del repo_config

        # multiple formats -- favored format is selected
        with open(self.metadata_path, 'w') as f:
            f.write('cache-formats = pms md5-dict\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format == 'md5-dict'
        del repo_config

        # unknown + known
        with open(self.metadata_path, 'w') as f:
            f.write('cache-formats = foo md5-dict\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.cache_format == 'md5-dict'
        del repo_config

    def test_profile_formats(self, caplog):
        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        del repo_config

        # explicit empty setting
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('profile-formats =\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        assert 'has explicitly unset profile-formats' in caplog.text
        caplog.clear()
        del repo_config

        # unknown formats
        with open(self.metadata_path, 'w') as f:
            f.write('profile-formats = foo bar\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        assert 'has unsupported profile format' in caplog.text
        caplog.clear()
        del repo_config

        # unknown + known
        with open(self.metadata_path, 'w') as f:
            f.write('profile-formats = foo portage-2\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms', 'portage-2'}
        assert 'has unsupported profile format' in caplog.text
        caplog.clear()
        del repo_config

        # known formats
        with open(self.metadata_path, 'w') as f:
            f.write('profile-formats = portage-1 portage-2\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'portage-1', 'portage-2'}
        del repo_config

    def test_pms_repo_name(self):
        os.mkdir(self.profiles_base)
        repo_name_path = os.path.join(self.profiles_base, 'repo_name')

        # nonexistent file
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name is None
        del repo_config

        # empty file
        touch(repo_name_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == ''
        del repo_config

        # whitespace
        with open(repo_name_path, 'w') as f:
            f.write(' \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == ''
        del repo_config

        # whitespace + name
        with open(repo_name_path, 'w') as f:
            f.write(' repo \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == 'repo'
        del repo_config

        # regular name
        with open(repo_name_path, 'w') as f:
            f.write('newrepo')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == 'newrepo'
        del repo_config

        # regular name EOLed
        with open(repo_name_path, 'w') as f:
            f.write('newrepo2\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == 'newrepo2'
        del repo_config

        # multi-line
        with open(repo_name_path, 'w') as f:
            f.write('newrepo3\nfoobar')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == 'newrepo3'
        del repo_config

        # binary data
        with open(repo_name_path, 'wb') as f:
            f.write(b'\x6e\x65\x77\x72\x65\x70\x6f\x34')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.pms_repo_name == 'newrepo4'
        del repo_config

    def test_repo_id(self, caplog):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.repo_id == "<unlabeled repo: 'nonexistent'>"
        del repo_config

        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == f"<unlabeled repo: {self.repo_path!r}>"
        assert caplog.text == ''
        caplog.clear()
        del repo_config

        # nonempty repo
        os.mkdir(self.profiles_base)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == f"<unlabeled repo: {self.repo_path!r}>"
        assert 'repo lacks a defined name:' in caplog.text
        caplog.clear()
        del repo_config

        # pms repo name exists
        with open(os.path.join(self.profiles_base, 'repo_name'), 'w') as f:
            f.write('pms_name')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == 'pms_name'
        del repo_config

        # layout.conf repo name exists
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('repo-name = metadata_name')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == 'metadata_name'
        del repo_config

        # config name exists
        repo_config = repo_objs.RepoConfig(self.repo_path, config_name='config_name')
        assert repo_config.repo_id == 'config_name'
        del repo_config

    def test_raw_known_arches(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.raw_known_arches == frozenset()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        arches_path = os.path.join(self.profiles_base, 'arch.list')
        touch(arches_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_known_arches == frozenset()
        del repo_config

        # single entry
        with open(arches_path, 'w') as f:
            f.write('foo')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_known_arches == frozenset(['foo'])
        del repo_config

        # multiple entries with whitespaces and comments
        with open(arches_path, 'w') as f:
            f.write(
                """
                amd64
                x86

                # prefix
                foo-bar
                """)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_known_arches == frozenset(['amd64', 'x86', 'foo-bar'])
        del repo_config

    def test_raw_use_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.raw_use_desc == ()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        use_desc_path = os.path.join(self.profiles_base, 'use.desc')
        touch(use_desc_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_use_desc == ()
        del repo_config

        # regular entries
        with open(use_desc_path, 'w') as f:
            f.write(
                """
                # copy
                # license

                foo1 - enable foo1
                foo2 - enable foo2
                bar3 - add bar3 support
                """)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert 3 == len(repo_config.raw_use_desc)
        del repo_config

    def test_raw_use_expand_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.raw_use_expand_desc == {}
        del repo_config

        # empty file
        use_expand_desc_path = os.path.join(self.profiles_base, 'desc')
        os.makedirs(use_expand_desc_path)
        use_expand_desc_file = os.path.join(use_expand_desc_path, 'foo.desc')
        touch(use_expand_desc_file)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_use_expand_desc == {'foo': ()}
        del repo_config

        # regular entries
        with open(use_expand_desc_file, 'w') as f:
            f.write(
                """
                # copy
                # license

                bar - add bar support
                baz - build using baz
                """)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_use_expand_desc == {
            'foo': (
                ('foo_bar', 'add bar support'),
                ('foo_baz', 'build using baz')
            )}
        del repo_config

    def test_raw_use_local_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.raw_use_local_desc == ()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        use_local_desc_path = os.path.join(self.profiles_base, 'use.local.desc')
        touch(use_local_desc_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.raw_use_local_desc == ()
        del repo_config

        # regular entries
        with open(use_local_desc_path, 'w') as f:
            f.write(
                """
                # copy
                # license

                cat/pkg1:foo1 - enable foo1
                cat1/pkg2:foo2 - enable foo2
                cat2/pkg3:bar3 - add bar3 support
                """)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert 3 == len(repo_config.raw_use_local_desc)
        del repo_config

    def test_updates(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.updates == {}
        del repo_config

        # empty file
        updates_path = os.path.join(self.profiles_base, 'updates')
        updates_file_path = os.path.join(updates_path, '1Q-2019')
        os.makedirs(updates_path)
        touch(updates_file_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.updates == {}
        del repo_config

        # simple pkg move
        # TODO: move pkg_updates content tests to its own module
        with open(updates_file_path, 'w') as f:
            f.write('move cat1/pkg1 cat2/pkg1\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.updates == {
            'cat1/pkg1':  [('move', atom.atom('cat1/pkg1'), atom.atom('cat2/pkg1'))],
        }
        del repo_config
