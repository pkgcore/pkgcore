import os
import textwrap
import urllib.error
import urllib.request
from os.path import join as pjoin

import pytest

from pkgcore.ebuild import overlays

REPOSITORIES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<repositories version="1.0">
  <repo quality="experimental" status="unofficial">
    <name>guru</name>
    <description lang="en">the GURU repository</description>
    <homepage>https://wiki.gentoo.org/wiki/Project:GURU</homepage>
    <source type="git">https://anongit.gentoo.org/git/repo/proj/guru.git</source>
    <source type="rsync">rsync://rsync.gentoo.org/guru</source>
  </repo>
  <repo>
    <name>hg-repo</name>
    <homepage>https://gentoo.org/hg</homepage>
    <source type="mercurial">https://gentoo.org/hg-repo</source>
  </repo>
  <repo>
    <name>cvs-only</name>
    <homepage>https://gentoo.org/cvs</homepage>
    <source type="cvs">:pserver:larry@gentoo.org:/cvsroot</source>
  </repo>
</repositories>
"""


class MockUrlopen:
    """Stand-in for urllib.request.urlopen, recording what it was asked for."""

    def __init__(self):
        self.headers = {}
        self._result = None

    def respond(self, data, etag=None):
        self._result = (data, etag)

    def fail(self, exc):
        self._result = exc

    def __call__(self, req, *args, **kwargs):
        # Request capitalizes header names, normalize them for the caller
        self.headers = {k.lower(): v for k, v in req.header_items()}
        if isinstance(self._result, Exception):
            raise self._result
        return MockResponse(*self._result)


class MockResponse:
    def __init__(self, data, etag):
        self._data = data
        self._etag = etag

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._data

    def getheader(self, name):
        return self._etag if name == "ETag" else None


@pytest.fixture
def mocked_urlopen(monkeypatch):
    mock = MockUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", mock)
    return mock


@pytest.fixture
def repositories_xml(tmp_path, monkeypatch, mocked_urlopen):
    """Serve the repository list from a cache under tmp_path."""
    monkeypatch.setattr(
        overlays, "_cache_path", lambda: str(tmp_path / "repositories.xml")
    )
    mocked_urlopen.respond(REPOSITORIES_XML.encode())


class TestRemoteRepos:
    def test_sources(self, repositories_xml):
        repos = overlays.remote_repos()
        assert set(repos) == {"guru", "hg-repo", "cvs-only"}
        guru = repos["guru"]
        assert guru.homepage == "https://wiki.gentoo.org/wiki/Project:GURU"
        # listed order is kept, since that's the order upstream prefers
        assert guru.sources == (
            ("git", "https://anongit.gentoo.org/git/repo/proj/guru.git"),
            ("rsync", "rsync://rsync.gentoo.org/guru"),
        )

    def test_mercurial_maps_to_hg(self, repositories_xml):
        assert overlays.remote_repos()["hg-repo"].sources == (
            ("hg", "https://gentoo.org/hg-repo"),
        )

    def test_unsupported_source_dropped(self, repositories_xml):
        assert overlays.remote_repos()["cvs-only"].sources == ()

    def test_malformed_xml(self, tmp_path, monkeypatch, mocked_urlopen):
        monkeypatch.setattr(
            overlays, "_cache_path", lambda: str(tmp_path / "repositories.xml")
        )
        mocked_urlopen.respond(b"<repositories>")
        with pytest.raises(overlays.RemoteRepoError, match="failed parsing"):
            overlays.remote_repos()


class TestFetch:
    uri = "https://gentoo.org/repositories.xml"

    @pytest.fixture
    def cache(self, tmp_path):
        return tmp_path / "repositories.xml"

    def test_initial_fetch(self, cache, mocked_urlopen):
        mocked_urlopen.respond(REPOSITORIES_XML.encode(), etag='"abc"')
        overlays._fetch(self.uri, str(cache))
        assert cache.read_text() == REPOSITORIES_XML
        assert cache.with_suffix(".xml.etag").read_text() == '"abc"'
        assert mocked_urlopen.headers == {}

    def test_conditional_request(self, cache, mocked_urlopen):
        mocked_urlopen.respond(REPOSITORIES_XML.encode(), etag='"abc"')
        overlays._fetch(self.uri, str(cache))

        mocked_urlopen.fail(
            urllib.error.HTTPError(self.uri, 304, "Not Modified", {}, None)
        )
        overlays._fetch(self.uri, str(cache))
        assert mocked_urlopen.headers["if-none-match"] == '"abc"'
        assert "if-modified-since" in mocked_urlopen.headers
        # the cached copy survived the 304
        assert cache.read_text() == REPOSITORIES_XML

    def test_failure_falls_back_to_cache(self, cache, mocked_urlopen):
        mocked_urlopen.respond(REPOSITORIES_XML.encode())
        overlays._fetch(self.uri, str(cache))

        mocked_urlopen.fail(urllib.error.URLError("no route to host"))
        overlays._fetch(self.uri, str(cache))
        assert cache.read_text() == REPOSITORIES_XML

    def test_failure_without_cache(self, cache, mocked_urlopen):
        mocked_urlopen.fail(urllib.error.URLError("no route to host"))
        with pytest.raises(overlays.RemoteRepoError, match="failed fetching"):
            overlays._fetch(self.uri, str(cache))


class TestConfiguredRepos:
    def test_dir(self, tmp_path):
        (path := tmp_path / "repos.conf").mkdir()
        (path / "gentoo.conf").write_text(
            "[DEFAULT]\nmain-repo = gentoo\n\n[gentoo]\nlocation = /var/db/repos/gentoo\n"
        )
        (path / "guru.conf").write_text("[guru]\nlocation = /var/db/repos/guru\n")
        # hidden and backup files are skipped, as they are when parsing
        (path / ".hidden.conf").write_text("[hidden]\n")
        (path / "old.conf~").write_text("[old]\n")
        repos = overlays.configured_repos(str(path))
        assert set(repos) == {"gentoo", "guru"}
        assert repos["guru"]["location"] == "/var/db/repos/guru"

    def test_file(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text("[gentoo]\n\n[guru]\n")
        assert set(overlays.configured_repos(str(path))) == {"gentoo", "guru"}

    def test_relative_location(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text("[stubrepo]\nlocation = ../repo\n")
        assert overlays.configured_repos(str(path))["stubrepo"]["location"] == str(
            tmp_path.parent / "repo"
        )

    def test_user_location(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text(
            "[gentoo]\nlocation = ~/.cache/pkgcore/repos/gentoo\n"
        )
        location = overlays.configured_repos(str(path))["gentoo"]["location"]
        assert location == os.path.expanduser("~/.cache/pkgcore/repos/gentoo")

    def test_nonexistent(self, tmp_path):
        assert overlays.configured_repos(str(tmp_path / "repos.conf")) == {}

    def test_malformed(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text("junk without a section\n")
        with pytest.raises(overlays.RemoteRepoError, match="failed parsing"):
            overlays.configured_repos(str(path))


class TestReposBase:
    def test_follows_the_synced_repos(self):
        configured = {
            "gentoo": {"location": "/var/db/repos/gentoo", "sync-uri": "git://..."},
            "local": {"location": "/home/user/repo"},
        }
        assert overlays.repos_base(configured) == "/var/db/repos"

    def test_follows_a_stub_style_config(self):
        """pkgcore's stub config keeps repos under the user cache, not /var/db."""
        configured = {
            "stubrepo": {"location": "/usr/share/pkgcore/stubrepo"},
            "gentoo": {
                "location": "/root/.cache/pkgcore/repos/gentoo",
                "sync-uri": "tar+https://...",
            },
        }
        assert overlays.repos_base(configured) == "/root/.cache/pkgcore/repos"

    def test_the_most_common_dir_wins(self):
        configured = {
            "odd": {"location": "/opt/odd", "sync-uri": "git://..."},
            "gentoo": {"location": "/var/db/repos/gentoo", "sync-uri": "git://..."},
            "guru": {"location": "/var/db/repos/guru", "sync-uri": "git://..."},
        }
        assert overlays.repos_base(configured) == "/var/db/repos"

    def test_nothing_to_go_on(self):
        assert overlays.repos_base({}) == overlays.FALLBACK_REPOS_BASE
        # a repo with no sync-uri says nothing about where synced repos live
        assert (
            overlays.repos_base({"local": {"location": "/home/user/repo"}})
            == overlays.FALLBACK_REPOS_BASE
        )


class TestAddReposConfEntry:
    entry = textwrap.dedent("""\
        [guru]
        location = /var/db/repos/guru
        sync-type = git
        sync-uri = https://gentoo.org/guru.git
    """)

    def add(self, path):
        return overlays.add_repos_conf_entry(
            str(path),
            "guru",
            "/var/db/repos/guru",
            "git",
            "https://gentoo.org/guru.git",
        )

    def test_dir_gets_a_file_per_repo(self, tmp_path):
        (path := tmp_path / "repos.conf").mkdir()
        assert self.add(path) == pjoin(str(path), "guru.conf")
        assert (path / "guru.conf").read_text() == self.entry

    def test_missing_path_becomes_a_dir(self, tmp_path):
        path = tmp_path / "repos.conf"
        assert self.add(path) == pjoin(str(path), "guru.conf")
        assert (path / "guru.conf").read_text() == self.entry

    def test_file_is_appended_to(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text("[gentoo]\n")
        assert self.add(path) == str(path)
        assert path.read_text() == "[gentoo]\n\n" + self.entry

    def test_file_keeps_a_single_blank_line(self, tmp_path):
        (path := tmp_path / "repos.conf").write_text("[gentoo]\n\n")
        self.add(path)
        assert path.read_text() == "[gentoo]\n\n" + self.entry

    def test_the_entry_parses_back(self, tmp_path):
        (path := tmp_path / "repos.conf").mkdir()
        self.add(path)
        assert set(overlays.configured_repos(str(path))) == {"guru"}
