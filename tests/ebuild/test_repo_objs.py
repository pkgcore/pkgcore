# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
import re

from snakeoil.data_source import data_source
from snakeoil.fileutils import touch

from pkgcore.ebuild import repo_objs


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
        # test empty.
        assert () == self.get_metadata_xml().maintainers

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

    def test_nonexistent_repo(self):
        # Newly configured, nonexistent repos shouldn't cause issues.
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.location == 'nonexistent'
        assert repo_config.repo_id == 'nonexistent'

    def test_pms_repo_name(self, tmpdir):
        repo = str(tmpdir)
        profiles_base = os.path.join(repo, 'profiles')
        os.mkdir(profiles_base)
        repo_name_path = os.path.join(profiles_base, 'repo_name')

        # nonexistent file
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name is None
        del repo_config

        # empty file
        touch(repo_name_path)
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == ''
        del repo_config

        # whitespace
        with open(repo_name_path, 'w') as f:
            f.write(' \n')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == ''
        del repo_config

        # whitespace + name
        with open(repo_name_path, 'w') as f:
            f.write(' repo \n')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == 'repo'
        del repo_config

        # regular name
        with open(repo_name_path, 'w') as f:
            f.write('newrepo')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == 'newrepo'
        del repo_config

        # regular name EOLed
        with open(repo_name_path, 'w') as f:
            f.write('newrepo2\n')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == 'newrepo2'
        del repo_config

        # multi-line
        with open(repo_name_path, 'w') as f:
            f.write('newrepo3\nfoobar')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == 'newrepo3'
        del repo_config

        # binary data
        with open(repo_name_path, 'wb') as f:
            f.write(b'\x6e\x65\x77\x72\x65\x70\x6f\x34')
        repo_config = repo_objs.RepoConfig(repo)
        assert repo_config.pms_repo_name == 'newrepo4'
        del repo_config
