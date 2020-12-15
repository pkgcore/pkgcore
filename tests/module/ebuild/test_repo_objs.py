import logging
import os
import re

import pytest
from snakeoil.data_source import data_source
from snakeoil.fileutils import touch
from snakeoil.mappings import ImmutableDict

from pkgcore.ebuild import atom, repo_objs
from pkgcore.repository import errors as repo_errors


class TestMetadataXml:

    @staticmethod
    def get_metadata_xml(maintainers=(), comments=(), local_use={},
                         longdescription=None, maint_type=None,
                         stabilize_allarches=False):
        cs = '\n'.join(comments)
        ms = us = ls = ""
        if maintainers:
            ms = []
            for x in maintainers:
                ms.append(f"<email>{x[0]}</email>")
                if len(x) > 1:
                    ms[-1] += f"\n<name>{x[1]}</name>"
                if len(x) > 2:
                    ms[-1] += f"\n<description>{x[2]}</description>"
                if len(x) > 3:
                    raise ValueError('maintainer data has too many fields')
            maint_type = (f'type="{maint_type}"' if maint_type is not None else '')
            ms = '\n'.join(f'<maintainer {maint_type}>{x}</maintainer>' for x in ms)
        if local_use:
            us = ['<use>']
            for flag, desc in local_use.items():
                us.append(f'<flag name="{flag}">{desc}</flag>')
            us.append('</use>')
            us = '\n'.join(us)
        if longdescription:
            ls = f"<longdescription>{longdescription}</longdescription>\n"
        sa = "<stabilize-allarches/>" if stabilize_allarches else ""
        s = \
f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
{cs}{ms}{us}{ls}{sa}</pkgmetadata>"""
        return repo_objs.MetadataXml(data_source(s.encode('utf-8')))

    def test_empty_maintainers(self):
        assert () == self.get_metadata_xml().maintainers

    def test_maintainer_needed(self):
        mx = self.get_metadata_xml(comments=('<!-- maintainer-needed -->',))
        assert mx.maintainers == ()

    def test_multiple_maintainers(self):
        names = ("foo@gmail.com", "monkeybone@gmail.com")
        mx = self.get_metadata_xml(maintainers=tuple((x,) for x in names))
        assert sorted(names) == sorted(map(str, mx.maintainers))
        assert "foo@gmail.com" in mx.maintainers
        assert "monkeybone@gmail.com" in mx.maintainers

    def test_maintainer_name_with_email(self):
        mx = self.get_metadata_xml(
            maintainers=(("funkymonkey@gmail.com", "funky monkey \N{SNOWMAN}"),))
        assert ("funky monkey \N{SNOWMAN} <funkymonkey@gmail.com>",) == \
            tuple(map(str, mx.maintainers))
        assert "funkymonkey@gmail.com" in mx.maintainers
        assert "funky monkey \N{SNOWMAN}" in mx.maintainers
        assert "funkymonkey@gmail.com" == mx.maintainers[0].email
        assert "funky monkey \N{SNOWMAN}" == mx.maintainers[0].name
        assert mx.maintainers[0].description is None
        assert mx.maintainers[0].maint_type is None

    def test_maintainer_with_desc(self):
        mx = self.get_metadata_xml(
            maintainers=(("foo@bar.com", "foobar", "Foobar"),))
        assert ("foobar <foo@bar.com> (Foobar)",) == tuple(map(str, mx.maintainers))
        assert "foo@bar.com" in mx.maintainers
        assert "foobar" in mx.maintainers
        assert "foo@bar.com" == mx.maintainers[0].email
        assert "foobar" == mx.maintainers[0].name
        assert "Foobar" == mx.maintainers[0].description
        assert mx.maintainers[0].maint_type is None

    def test_maintainer_with_type(self):
        mx = self.get_metadata_xml(
            maintainers=(("foo@bar.com", "foobar"),),
            maint_type='person')
        assert ("foobar <foo@bar.com>",) == tuple(map(str, mx.maintainers))
        assert "foo@bar.com" in mx.maintainers
        assert "foobar" in mx.maintainers
        assert "foo@bar.com" == mx.maintainers[0].email
        assert "foobar" == mx.maintainers[0].name
        assert mx.maintainers[0].description is None
        assert "person" == mx.maintainers[0].maint_type

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

    def test_stabilize_allarches(self):
        # missing
        assert False == self.get_metadata_xml().stabilize_allarches
        # present
        assert True == self.get_metadata_xml(stabilize_allarches=True).stabilize_allarches


class TestProjectsXml:

    @staticmethod
    def get_projects_xml(s=None):
        default_s = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE projects SYSTEM "http://www.gentoo.org/dtd/projects.dtd">
<projects>
  <project>
    <email>nomembers@example.com</email>
    <name>Project with no members</name>
    <url>https://projects.example.com/nomembers</url>
    <description>Here is the description</description>
  </project>
  <project>
    <email>nolead@example.com</email>
    <name>Project with no lead</name>
    <url>https://projects.example.com/nolead</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev1@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <member>
      <email>dev1@example.com</email>
    </member>
  </project>
  <project>
    <email>lead@example.com</email>
    <name>Project with a lead</name>
    <url>https://projects.example.com/lead</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev2@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <member is-lead="1">
      <email>dev2@example.com</email>
    </member>
  </project>
  <project>
    <email>subprojects@example.com</email>
    <name>Project with non-recursive subprojects</name>
    <url>https://projects.example.com/subprojects</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev3@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <member is-lead="1">
      <email>dev3@example.com</email>
    </member>
    <subproject ref="nolead@example.com"/>
    <subproject ref="lead@example.com"/>
  </project>
  <project>
    <email>recursive-subprojects@example.com</email>
    <name>Project with recursive subprojects</name>
    <url>https://projects.example.com/recursive-subprojects</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev4@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <member>
      <!-- this one is common -->
      <email>dev1@example.com</email>
    </member>
    <member is-lead="1">
      <email>dev4@example.com</email>
    </member>
    <subproject ref="nolead@example.com" inherit-members="1"/>
    <subproject ref="lead@example.com"/>
  </project>
  <project>
    <email>super-recursive-subprojects@example.com</email>
    <name>Project with double recursion</name>
    <url>https://projects.example.com/super-recursive-subprojects</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev5@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <member is-lead="1">
      <!-- this one is common -->
      <email>dev2@example.com</email>
    </member>
    <member>
      <email>dev5@example.com</email>
    </member>
    <subproject ref="recursive-subprojects@example.com" inherit-members="1"/>
  </project>
</projects>"""
        if s is None:
            s = default_s
        return repo_objs.ProjectsXml(data_source(s.encode('utf-8')))

    def test_empty(self):
        assert self.get_projects_xml('').projects == {}

    def test_invalid_xml(self):
        assert self.get_projects_xml('<foo><bar></foo>').projects == {}

    def test_project_member_without_email(self):
        p = self.get_projects_xml("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE projects SYSTEM "http://www.gentoo.org/dtd/projects.dtd">
<projects>
  <project>
    <email>nolead@example.com</email>
    <name>Project with no lead</name>
    <url>https://projects.example.com/nolead</url>
    <description>Here is the description</description>
    <member>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
  </project>
</projects>
""").projects['nolead@example.com']
        assert p.members == ()

    def test_subproject_without_ref(self):
        p = self.get_projects_xml("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE projects SYSTEM "http://www.gentoo.org/dtd/projects.dtd">
<projects>
  <project>
    <email>nolead@example.com</email>
    <name>Project with no lead</name>
    <url>https://projects.example.com/nolead</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev1@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <subproject inherit-members="1"/>
  </project>
</projects>
""").projects['nolead@example.com']
        assert p.subprojects == ()

    def test_subproject_with_invalid_ref(self):
        p = self.get_projects_xml("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE projects SYSTEM "http://www.gentoo.org/dtd/projects.dtd">
<projects>
  <project>
    <email>nolead@example.com</email>
    <name>Project with no lead</name>
    <url>https://projects.example.com/nolead</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev1@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <subproject ref="nonexist@example.com" inherit-members="1"/>
  </project>
</projects>
""").projects['nolead@example.com']
        assert p.subprojects[0].project is None
        assert p.recursive_members == p.members

    def test_deep_subproject_with_invalid_ref(self):
        p = self.get_projects_xml("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE projects SYSTEM "http://www.gentoo.org/dtd/projects.dtd">
<projects>
  <project>
    <email>nolead@example.com</email>
    <name>Project with no lead</name>
    <url>https://projects.example.com/nolead</url>
    <description>Here is the description</description>
    <member>
      <email>fulldev1@example.com</email>
      <name>Full Dev</name>
      <role>Somebody</role>
    </member>
    <subproject ref="nonexist@example.com" inherit-members="1"/>
  </project>
  <project>
    <email>subprojects@example.com</email>
    <name>Project with real subprojects</name>
    <url>https://projects.example.com/subprojects</url>
    <description>Here is the description</description>
    <subproject ref="nolead@example.com" inherit-members="1"/>
  </project>
</projects>
""").projects
        assert (p['subprojects@example.com'].recursive_members ==
                p['nolead@example.com'].members)

    def test_basic_metadata(self):
        projects = self.get_projects_xml().projects
        for email, project in projects.items():
            assert project.email == email
            assert project.name.startswith('Project with')
            assert project.url == (
                'https://projects.example.com/' + email.split('@')[0])
            assert project.description == 'Here is the description'

    def test_no_members(self):
        p = self.get_projects_xml().projects['nomembers@example.com']
        assert p.members == ()
        assert p.leads == ()
        assert p.subprojects == ()
        assert p.recursive_members == ()

    def test_no_lead(self):
        p = self.get_projects_xml().projects['nolead@example.com']
        assert p.members[0].email == 'fulldev1@example.com'
        assert p.members[0].name == 'Full Dev'
        assert p.members[0].role == 'Somebody'
        assert not p.members[0].is_lead
        assert p.members[1].email == 'dev1@example.com'
        assert p.members[1].name is None
        assert p.members[1].role is None
        assert not p.members[1].is_lead
        assert p.leads == ()
        assert p.subprojects == ()
        assert p.recursive_members == p.members

    def test_have_lead(self):
        p = self.get_projects_xml().projects['lead@example.com']
        assert p.members[0].email == 'fulldev2@example.com'
        assert p.members[0].name == 'Full Dev'
        assert p.members[0].role == 'Somebody'
        assert not p.members[0].is_lead
        assert p.members[1].email == 'dev2@example.com'
        assert p.members[1].name is None
        assert p.members[1].role is None
        assert p.members[1].is_lead
        assert p.leads == (p.members[1],)
        assert p.subprojects == ()
        assert p.recursive_members == p.members

    def test_subprojects(self):
        p = self.get_projects_xml().projects['subprojects@example.com']
        assert p.subprojects[0].email == 'nolead@example.com'
        assert p.subprojects[0].name == 'Project with no lead'
        assert not p.subprojects[0].inherit_members
        assert p.subprojects[1].email == 'lead@example.com'
        assert p.subprojects[1].name == 'Project with a lead'
        assert not p.subprojects[1].inherit_members
        assert p.recursive_members == p.members

    @staticmethod
    def unlead(members):
        for m in members:
            yield repo_objs.ProjectMember(
                email=m.email, name=m.name, role=m.role, is_lead=False)

    def test_recursive_subprojects(self):
        projects = self.get_projects_xml().projects
        p = projects['recursive-subprojects@example.com']
        sp = projects['nolead@example.com']
        assert p.subprojects[0].email == 'nolead@example.com'
        assert p.subprojects[0].name == 'Project with no lead'
        assert p.subprojects[0].inherit_members
        assert p.subprojects[1].email == 'lead@example.com'
        assert p.subprojects[1].name == 'Project with a lead'
        assert not p.subprojects[1].inherit_members
        # one extra member should be inherited from sp
        assert p.recursive_members == (
            p.members + tuple(self.unlead(sp.members[:1])))
        # lead of sp should not be considered lead of p
        assert not p.recursive_members[3].is_lead

    def test_super_recursive_subprojects(self):
        projects = self.get_projects_xml().projects
        p = projects['super-recursive-subprojects@example.com']
        sp = projects['recursive-subprojects@example.com']
        ssp = projects['nolead@example.com']
        assert p.subprojects[0].email == 'recursive-subprojects@example.com'
        assert p.subprojects[0].name == 'Project with recursive subprojects'
        assert p.subprojects[0].inherit_members
        # one extra member should be inherited from ssp
        assert p.recursive_members == (
            p.members + tuple(self.unlead(sp.members + ssp.members[:1])))
        # lead of sp should not be considered lead of p
        assert not p.recursive_members[5].is_lead


class TestRepoConfig:

    @pytest.fixture(autouse=True)
    def _setup(self, tmpdir):
        self.repo_path = str(tmpdir)
        self.profiles_base = os.path.join(self.repo_path, 'profiles')
        self.metadata_path = os.path.join(
            self.repo_path, repo_objs.RepoConfig.layout_offset)
        self.eapi_path = os.path.join(self.profiles_base, 'eapi')

    def test_nonexistent_repo(self):
        # Newly configured, nonexistent repos shouldn't cause issues.
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.location == 'nonexistent'

    def test_default_eapi(self):
        os.mkdir(self.profiles_base)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'

    def test_empty_file_eapi(self):
        os.mkdir(self.profiles_base)
        touch(self.eapi_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'

    def test_empty_content_eapi(self):
        os.mkdir(self.profiles_base)
        with open(self.eapi_path, 'w+') as f:
            f.write('     \n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '0'

    def test_unknown_eapi(self):
        os.mkdir(self.profiles_base)
        with open(self.eapi_path, 'w+') as f:
            f.write('unknown_eapi')
        with pytest.raises(repo_errors.UnsupportedRepo) as excinfo:
            repo_objs.RepoConfig(self.repo_path)
        assert isinstance(excinfo.value.repo, repo_objs.RepoConfig)

    def test_known_eapi(self):
        os.mkdir(self.profiles_base)
        with open(self.eapi_path, 'w+') as f:
            f.write('6')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '6'

    def test_bad_data_known_eapi(self, caplog):
        os.mkdir(self.profiles_base)
        with open(self.eapi_path, 'w+') as f:
            f.write('4\nfoo\nbar')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert str(repo_config.eapi) == '4'
        assert 'multiple lines detected' in caplog.text

    def test_bad_data_unknown_eapi(self, caplog):
        os.mkdir(self.profiles_base)
        with open(self.eapi_path, 'w+') as f:
            f.write('eapi\nfoo\nbar')
        with pytest.raises(repo_errors.UnsupportedRepo) as excinfo:
            repo_objs.RepoConfig(self.repo_path)
        assert isinstance(excinfo.value.repo, repo_objs.RepoConfig)
        assert 'multiple lines detected' in caplog.text

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
        os.mkdir(self.profiles_base)
        with open(os.path.join(self.profiles_base, 'repo_name'), 'w') as f:
            f.write('pms_name')

        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        del repo_config
        caplog.clear()

        # explicit empty setting
        os.mkdir(os.path.dirname(self.metadata_path))
        with open(self.metadata_path, 'w') as f:
            f.write('masters =\nprofile-formats =\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        assert not caplog.text
        caplog.clear()
        del repo_config
        # message shown at info log level
        caplog.set_level(logging.INFO)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert 'has explicitly unset profile-formats' in caplog.text
        caplog.clear()
        del repo_config

        # unknown formats
        caplog.set_level(logging.WARNING)
        with open(self.metadata_path, 'w') as f:
            f.write('masters =\nprofile-formats = foo bar\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms'}
        assert not caplog.text
        caplog.clear()
        del repo_config
        # message shown at info log level
        caplog.set_level(logging.INFO)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert 'has unsupported profile format' in caplog.text
        caplog.clear()
        del repo_config

        # unknown + known
        caplog.set_level(logging.WARNING)
        with open(self.metadata_path, 'w') as f:
            f.write('masters =\nprofile-formats = foo portage-2\n')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.profile_formats == {'pms', 'portage-2'}
        assert not caplog.text
        caplog.clear()
        del repo_config
        # message shown at info log level
        caplog.set_level(logging.INFO)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert 'has unsupported profile format' in caplog.text
        caplog.clear()
        del repo_config

        # known formats
        caplog.set_level(logging.WARNING)
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
        assert repo_config.repo_id == 'nonexistent'
        del repo_config

        # empty repo
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == self.repo_path
        assert caplog.text == ''
        caplog.clear()
        del repo_config

        # nonempty repo
        os.mkdir(self.profiles_base)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.repo_id == self.repo_path
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

    def test_known_arches(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.known_arches == frozenset()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        arches_path = os.path.join(self.profiles_base, 'arch.list')
        touch(arches_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.known_arches == frozenset()
        del repo_config

        # single entry
        with open(arches_path, 'w') as f:
            f.write('foo')
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.known_arches == frozenset(['foo'])
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
        assert repo_config.known_arches == frozenset(['amd64', 'x86', 'foo-bar'])
        del repo_config

    def test_arches_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        empty = {'stable': set(), 'transitional': set(), 'testing': set()}
        assert repo_config.arches_desc == ImmutableDict(empty)
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        arches_desc_path = os.path.join(self.profiles_base, 'arches.desc')
        touch(arches_desc_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.arches_desc == ImmutableDict(empty)
        del repo_config

        # regular entries
        with open(os.path.join(self.profiles_base, 'arch.list'), 'w') as f:
            f.write(
                """
                amd64
                alpha
                foo
                """)
        with open(arches_desc_path, 'w') as f:
            f.write(
                """
                # arches.desc file

                amd64 stable
                alpha testing
                """)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.arches_desc['stable'] == {'amd64'}
        assert repo_config.arches_desc['testing'] == {'alpha'}
        assert repo_config.arches_desc['transitional'] == set()
        del repo_config

    def test_use_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.use_desc == ()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        use_desc_path = os.path.join(self.profiles_base, 'use.desc')
        touch(use_desc_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.use_desc == ()
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
        assert 3 == len(repo_config.use_desc)
        del repo_config

    def test_use_expand_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.use_expand_desc == {}
        del repo_config

        # empty file
        use_expand_desc_path = os.path.join(self.profiles_base, 'desc')
        os.makedirs(use_expand_desc_path)
        use_expand_desc_file = os.path.join(use_expand_desc_path, 'foo.desc')
        touch(use_expand_desc_file)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.use_expand_desc == {'foo': ()}
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
        assert repo_config.use_expand_desc == {
            'foo': (
                ('foo_bar', 'add bar support'),
                ('foo_baz', 'build using baz')
            )}
        del repo_config

    def test_use_local_desc(self):
        # nonexistent repo
        repo_config = repo_objs.RepoConfig('nonexistent')
        assert repo_config.use_local_desc == ()
        del repo_config

        # empty file
        os.mkdir(self.profiles_base)
        use_local_desc_path = os.path.join(self.profiles_base, 'use.local.desc')
        touch(use_local_desc_path)
        repo_config = repo_objs.RepoConfig(self.repo_path)
        assert repo_config.use_local_desc == ()
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
        assert 3 == len(repo_config.use_local_desc)
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
