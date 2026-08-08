import pytest
from snakeoil.cli import arghparse

from pkgcore.bugzilla.apikey import (
    API_KEY_ENV,
    BugzillaApiKey,
    BugzillaClientArgs,
    find_api_key,
)
from pkgcore.bugzilla.client import DEFAULT_URL, Bugzilla
from pkgcore.bugzilla.errors import BugzillaUsageError


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)


class TestFindApiKey:
    def test_nothing_configured(self, tmp_path):
        assert find_api_key(home=tmp_path) is None

    def test_explicit_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        (tmp_path / ".bugz_token").write_text("from-file")
        assert find_api_key("explicit", home=tmp_path) == "explicit"

    def test_explicit_is_stripped(self, tmp_path):
        assert find_api_key("  key  ", home=tmp_path) == "key"

    def test_blank_explicit_falls_through(self, tmp_path):
        (tmp_path / ".bugz_token").write_text("from-file")
        assert find_api_key("   ", home=tmp_path) == "from-file"

    def test_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        (tmp_path / ".bugz_token").write_text("from-file")
        assert find_api_key(home=tmp_path) == "from-env"

    def test_env_can_be_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        assert find_api_key(allow_env=False, home=tmp_path) is None

    def test_blank_env_falls_through(self, tmp_path, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "  ")
        (tmp_path / ".bugz_token").write_text("from-file")
        assert find_api_key(home=tmp_path) == "from-file"

    @pytest.mark.parametrize("section", ("default", "gentoo", "Gentoo"))
    def test_bugzrc_sections(self, tmp_path, section):
        (tmp_path / ".bugzrc").write_text(f"[{section}]\nkey = rc-key\n")
        assert find_api_key(home=tmp_path) == "rc-key"

    def test_bugzrc_beats_token_file(self, tmp_path):
        (tmp_path / ".bugzrc").write_text("[default]\nkey = rc-key\n")
        (tmp_path / ".bugz_token").write_text("token-key")
        assert find_api_key(home=tmp_path) == "rc-key"

    def test_bugzrc_without_a_key_falls_through(self, tmp_path):
        (tmp_path / ".bugzrc").write_text("[default]\nuser = someone\n")
        (tmp_path / ".bugz_token").write_text("token-key")
        assert find_api_key(home=tmp_path) == "token-key"

    def test_empty_bugzrc_value_is_not_a_key(self, tmp_path):
        (tmp_path / ".bugzrc").write_text("[default]\nkey =\n")
        (tmp_path / ".bugz_token").write_text("token-key")
        assert find_api_key(home=tmp_path) == "token-key"

    def test_unrelated_section_is_ignored(self, tmp_path):
        (tmp_path / ".bugzrc").write_text("[somewhere-else]\nkey = nope\n")
        assert find_api_key(home=tmp_path) is None

    def test_malformed_bugzrc(self, tmp_path):
        (tmp_path / ".bugzrc").write_text("this is not ini\n[unclosed\n")
        with pytest.raises(BugzillaUsageError, match="failed parsing"):
            find_api_key(home=tmp_path)

    def test_token_file(self, tmp_path):
        (tmp_path / ".bugz_token").write_text("  token-key\n")
        assert find_api_key(home=tmp_path) == "token-key"

    def test_empty_token_file(self, tmp_path):
        (tmp_path / ".bugz_token").write_text("\n")
        assert find_api_key(home=tmp_path) is None

    def test_warns_on_world_readable_file(self, tmp_path, caplog):
        token = tmp_path / ".bugz_token"
        token.write_text("token-key")
        token.chmod(0o644)
        assert find_api_key(home=tmp_path) == "token-key"
        assert "readable by others" in caplog.text

    def test_no_warning_when_private(self, tmp_path, caplog):
        token = tmp_path / ".bugz_token"
        token.write_text("token-key")
        token.chmod(0o600)
        find_api_key(home=tmp_path)
        assert "readable by others" not in caplog.text


class TestBugzillaApiKey:
    @pytest.fixture
    def parser(self):
        parser = arghparse.ArgumentParser(suppress=True)
        BugzillaApiKey.mangle_argparser(parser)
        return parser

    def test_explicit_option(self, parser, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        namespace = parser.parse_args(["--api-key", "cli-key"])
        assert namespace.api_key == "cli-key"

    def test_falls_back_to_discovery(self, parser, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        assert parser.parse_args([]).api_key == "from-env"

    def test_anonymous(self, parser, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert parser.parse_args([]).api_key is None


class TestBugzillaClientArgs:
    @pytest.fixture
    def parser(self):
        parser = arghparse.ArgumentParser(suppress=True)
        BugzillaClientArgs.mangle_argparser(parser)
        return parser

    def test_builds_a_client(self, parser, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        namespace = parser.parse_args([])
        assert isinstance(namespace.bugzilla, Bugzilla)
        assert namespace.bugzilla.base_url == DEFAULT_URL

    def test_custom_url(self, parser, monkeypatch):
        monkeypatch.setenv(API_KEY_ENV, "from-env")
        namespace = parser.parse_args(["--bugzilla-url", "https://bugs.example.org/"])
        assert namespace.bugzilla.base_url == "https://bugs.example.org"

    def test_api_key_is_resolved_first(self, parser, tmp_path, monkeypatch):
        # the client's delayed default has a lower priority than the key's
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        namespace = parser.parse_args(["--api-key", "cli-key"])
        assert namespace.api_key == "cli-key"
        assert isinstance(namespace.bugzilla, Bugzilla)
